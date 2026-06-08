"""Ingestion endpoints.

POST /api/ingest/file          (multipart upload)
POST /api/ingest/path          (local filesystem path)
POST /api/ingest/repo          (local repo path)
GET  /api/documents            list
GET  /api/documents/{id}       detail
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from collections import Counter
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.rate_limiter import limiter

from app.claude.event_bus import drain, publish, subscribe, unsubscribe
from app.ingest.bulk import WorkItem, plan_bulk
from app.ingest.path_guard import is_blocked_path
from app.ingest.pipeline import (
    _sha256_file,
    _sha256_repo,
    ingest,
    ingest_repo,
)
from app.storage import documents_store

router = APIRouter(prefix="/api")
log = logging.getLogger("tank.routers.ingest")


class IngestPathRequest(BaseModel):
    path: str
    category: str = "auto"
    project_id: str | None = None


class IngestRepoRequest(BaseModel):
    path: str
    category: str = "code"
    project_id: str | None = None


def _do_ingest_file(path: Path, category: str, project_id: str | None = None) -> None:
    try:
        ingest(path, category=category)
    except Exception:
        log.exception("ingest failed for %s", path)  # status='error' recorded
    finally:
        # Clean up temp upload dirs created by ingest_file().
        # Regular path/repo ingests use the user's own filesystem — don't touch.
        if "tank-upload-" in str(path.parent):
            shutil.rmtree(path.parent, ignore_errors=True)
    if project_id:
        from app.storage.projects_store import touch_activity
        touch_activity(project_id)


def _do_ingest_repo(path: Path, category: str, project_id: str | None = None) -> None:
    try:
        ingest_repo(path, category=category)
    except Exception:
        log.exception("ingest_repo failed for %s", path)
    if project_id:
        from app.storage.projects_store import touch_activity
        touch_activity(project_id)


_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post("/ingest/file")
@limiter.limit("30/minute")
async def ingest_file(request: Request,
                      background_tasks: BackgroundTasks,
                      file: UploadFile = File(...),
                      category: str = Form(...),
                      project_id: str = Form(default="")) -> dict:
    if category not in {"architecture", "code", "cmdb", "people_process"}:
        raise HTTPException(400, f"invalid category {category}")

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (max 100 MB)")

    safe_name = os.path.basename(file.filename or "upload").lstrip(".")[:200]
    tmpdir = tempfile.mkdtemp(prefix="tank-upload-")
    target = Path(tmpdir) / (safe_name or "upload")
    with target.open("wb") as fh:
        fh.write(content)

    pid = project_id.strip() or None
    background_tasks.add_task(_do_ingest_file, target, category, pid)
    return {"status": "queued", "path": str(target)}


_ALLOWED_INGEST_ROOTS: list[Path] = [Path.home()]


@router.post("/ingest/path")
@limiter.limit("30/minute")
async def ingest_path(request: Request,
                      req: IngestPathRequest,
                      background_tasks: BackgroundTasks) -> dict:
    p = Path(req.path).expanduser().resolve()
    if not any(p == r or str(p).startswith(str(r) + os.sep)
               for r in _ALLOWED_INGEST_ROOTS):
        raise HTTPException(403, "path outside allowed ingest directories")
    blocked = is_blocked_path(p)
    if blocked:
        log.warning("blocked ingest path attempt: %s (matched: %s)", p, blocked)
        raise HTTPException(403, "path not allowed")
    if not p.exists():
        raise HTTPException(404, f"no such path: {req.path}")

    if p.is_dir():
        from app.ingest.auto_categorize import walk_directory
        pairs = walk_directory(p)
        if not pairs:
            raise HTTPException(422, "no parseable files found in directory")
        queued_files = []
        for file_path, auto_cat in pairs:
            cat = auto_cat if req.category == "auto" else req.category
            background_tasks.add_task(_do_ingest_file, file_path, cat)
            queued_files.append({"path": str(file_path.relative_to(p)), "category": cat})
        return {"status": "queued", "queued": len(pairs), "files": queued_files}

    cat = req.category
    if cat == "auto":
        from app.ingest.auto_categorize import suggest_category
        cat = suggest_category(p)
    background_tasks.add_task(_do_ingest_file, p, cat)
    return {"status": "queued", "path": str(p)}


@router.post("/ingest/repo")
@limiter.limit("10/minute")
async def ingest_repo_endpoint(request: Request,
                               req: IngestRepoRequest,
                               background_tasks: BackgroundTasks) -> dict:
    p = Path(req.path).expanduser().resolve()
    if not any(p == r or str(p).startswith(str(r) + os.sep)
               for r in _ALLOWED_INGEST_ROOTS):
        raise HTTPException(403, "path outside allowed ingest directories")
    blocked = is_blocked_path(p)
    if blocked:
        raise HTTPException(403, f"path not allowed (sensitive directory: {blocked})")
    if not p.is_dir():
        raise HTTPException(404, f"no such directory: {req.path}")
    background_tasks.add_task(_do_ingest_repo, p, req.category)
    return {"status": "queued", "path": str(p)}


# ---------------- bulk ingest (drag-drop / mixed paths + SSE) ----------------

class BulkPathRequest(BaseModel):
    paths: list[str] = Field(max_length=500)
    project_id: str | None = None


def _safe_rel(rel: str) -> Path:
    """Sanitize a browser-supplied relative path (webkitRelativePath).
    Drops absolute roots and any ``..`` traversal segments."""
    parts = [seg for seg in PurePosixPath(rel).parts
             if seg not in ("", ".", "..") and not seg.startswith("/")]
    return Path(*parts) if parts else Path("upload")


@router.post("/ingest/bulk-path")
@limiter.limit("10/minute")
async def ingest_bulk_path(request: Request, req: BulkPathRequest) -> dict:
    """Plan a mixed-path bulk ingest (files / folders / repos) from local
    filesystem paths. Returns a task_id to stream progress from."""
    validated: list[Path] = []
    for raw in req.paths:
        p = Path(raw).expanduser().resolve()
        if not any(p == r or str(p).startswith(str(r) + os.sep)
                   for r in _ALLOWED_INGEST_ROOTS):
            raise HTTPException(403, f"path outside allowed ingest directories: {raw}")
        blocked = is_blocked_path(p)
        if blocked:
            log.warning("blocked ingest path attempt: %s (matched: %s)", p, blocked)
            raise HTTPException(403, "path not allowed")
        if not p.exists():
            raise HTTPException(404, f"no such path: {raw}")
        validated.append(p)

    items = plan_bulk(validated)
    if not items:
        raise HTTPException(422, "no ingestable files or repos found")

    task_id = uuid.uuid4().hex
    pid = (req.project_id or "").strip() or None
    asyncio.create_task(_run_bulk_ingest_task(task_id, items, pid))
    return {"task_id": task_id, "planned": len(items)}


@router.post("/ingest/bulk-upload")
@limiter.limit("10/minute")
async def ingest_bulk_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    rel_paths: str = Form(default="[]"),
    project_id: str = Form(default=""),
) -> dict:
    """Plan a bulk ingest from drag-dropped files/folders. The browser
    sends each file plus a parallel ``rel_paths`` array (webkitRelativePath)
    so folder structure — and therefore repo detection + per-subfolder
    categorization — is preserved under a temp dir."""
    try:
        rels = json.loads(rel_paths) if rel_paths else []
    except json.JSONDecodeError:
        rels = []

    tmpdir = Path(tempfile.mkdtemp(prefix="tank-upload-"))
    try:
        for idx, uf in enumerate(files):
            content = await uf.read(_MAX_UPLOAD_BYTES + 1)
            if len(content) > _MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"file too large (max 100 MB): {uf.filename}")
            rel = rels[idx] if idx < len(rels) and rels[idx] else \
                os.path.basename(uf.filename or f"upload-{idx}")
            target = tmpdir / _safe_rel(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as fh:
                fh.write(content)
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

    items = plan_bulk([tmpdir])
    if not items:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(422, "no ingestable files or repos found")

    task_id = uuid.uuid4().hex
    pid = project_id.strip() or None
    asyncio.create_task(_run_bulk_ingest_task(task_id, items, pid, cleanup_dir=tmpdir))
    return {"task_id": task_id, "planned": len(items)}


@router.get("/ingest/bulk/{task_id}/stream")
async def bulk_stream(task_id: str):
    """SSE stream of per-item progress + a final analysis summary."""
    topic = f"ingest.{task_id}"
    q = subscribe(topic)

    async def event_source():
        try:
            async for ev in drain(q, idle_timeout=120.0):
                if ev is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": ev.kind, "data": json.dumps(ev.payload, default=str)}
                if ev.kind in {"done", "error"}:
                    break
        finally:
            unsubscribe(topic, q)

    return EventSourceResponse(event_source())


def _ingest_file_dedup(path: Path, category: str) -> bool:
    """Ingest one file; return True if it was a sha256 duplicate (skipped)."""
    sha, _ = _sha256_file(path)
    existed = documents_store.find_by_sha256(sha) is not None
    ingest(path, category=category)
    return existed


def _ingest_repo_dedup(path: Path, category: str) -> bool:
    sha = _sha256_repo(path)
    existed = documents_store.find_by_sha256(sha) is not None
    ingest_repo(path, category=category)
    return existed


async def _run_bulk_ingest_task(task_id: str, items: list[WorkItem],
                                project_id: str | None,
                                cleanup_dir: Path | None = None) -> None:
    """Run a planned bulk ingest, streaming per-item progress to
    ``ingest.{task_id}``. Each (synchronous) pipeline call is offloaded to
    a thread so the SSE heartbeat keeps flowing during long ingests."""
    topic = f"ingest.{task_id}"
    loop = asyncio.get_event_loop()
    repos = sum(1 for i in items if i.kind == "repo")
    file_count = len(items) - repos
    by_plan = Counter(i.category for i in items)

    # Brief grace period so the browser's EventSource subscribes before the
    # first event is published (the in-process bus does not buffer).
    await asyncio.sleep(0.3)

    publish(topic, "plan", {
        "total": len(items), "files": file_count, "repos": repos,
        "by_category": dict(by_plan),
    })

    ingested = skipped = errors = 0
    try:
        for idx, item in enumerate(items):
            label = item.rel_label()
            publish(topic, "item", {
                "index": idx, "name": label, "kind": item.kind,
                "category": item.category, "status": "started",
            })
            try:
                fn = _ingest_repo_dedup if item.kind == "repo" else _ingest_file_dedup
                was_dup = await loop.run_in_executor(
                    None, fn, item.path, item.category)
                if was_dup:
                    skipped += 1
                    status = "skipped"
                else:
                    ingested += 1
                    status = "done"
                publish(topic, "item", {
                    "index": idx, "name": label, "kind": item.kind,
                    "category": item.category, "status": status,
                })
            except Exception as exc:  # noqa: BLE001 — surface per-item, keep going
                errors += 1
                log.exception("bulk ingest item failed: %s", item.path)
                publish(topic, "item", {
                    "index": idx, "name": label, "kind": item.kind,
                    "status": "error", "error": str(exc),
                })

        if project_id:
            from app.storage.projects_store import touch_activity
            touch_activity(project_id)

        publish(topic, "done", {
            "ingested": ingested, "repos": repos,
            "skipped": skipped, "errors": errors,
            "by_category": documents_store.count_by_category(),
        })
    except Exception as exc:
        log.exception("bulk ingest task %s failed", task_id)
        publish(topic, "error", {"error": str(exc)})
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


@router.get("/documents")
def list_documents(category: str | None = None) -> dict:
    docs = documents_store.list_documents(category=category)
    return {"documents": docs, "counts": documents_store.count_by_category()}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str) -> dict:
    doc = documents_store.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "no such document")
    return doc
