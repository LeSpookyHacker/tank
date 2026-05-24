"""Ingestion endpoints.

POST /api/ingest/file          (multipart upload)
POST /api/ingest/path          (local filesystem path)
POST /api/ingest/repo          (local repo path)
GET  /api/documents            list
GET  /api/documents/{id}       detail
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.ingest.pipeline import ingest, ingest_repo
from app.storage import documents_store

router = APIRouter(prefix="/api")


class IngestPathRequest(BaseModel):
    path: str
    category: str = "auto"   # 'auto' triggers smart categorization


class IngestRepoRequest(BaseModel):
    path: str
    category: str = "code"


def _do_ingest_file(path: Path, category: str) -> None:
    try:
        ingest(path, category=category)
    except Exception:
        pass  # status='error' already recorded in documents


def _do_ingest_repo(path: Path, category: str) -> None:
    try:
        ingest_repo(path, category=category)
    except Exception:
        pass


@router.post("/ingest/file")
async def ingest_file(background_tasks: BackgroundTasks,
                      file: UploadFile = File(...),
                      category: str = Form(...)) -> dict:
    if category not in {"architecture", "code", "cmdb", "people_process"}:
        raise HTTPException(400, f"invalid category {category}")

    # Persist upload to a temp file; ingest reads it from there.
    tmpdir = tempfile.mkdtemp(prefix="tank-upload-")
    target = Path(tmpdir) / (file.filename or "upload")
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    background_tasks.add_task(_do_ingest_file, target, category)
    return {"status": "queued", "path": str(target)}


@router.post("/ingest/path")
async def ingest_path(req: IngestPathRequest,
                      background_tasks: BackgroundTasks) -> dict:
    p = Path(req.path).expanduser()
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
async def ingest_repo_endpoint(req: IngestRepoRequest,
                               background_tasks: BackgroundTasks) -> dict:
    p = Path(req.path).expanduser()
    if not p.is_dir():
        raise HTTPException(404, f"no such directory: {req.path}")
    background_tasks.add_task(_do_ingest_repo, p, req.category)
    return {"status": "queued", "path": str(p)}


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
