"""DFD threat modeling endpoints — DFD & Threat Model revamp.

Routes:
  GET  /dfd                                 Stage 1 input page
  GET  /dfd/{dfd_id}                        Stage 3 output workspace
  POST /api/dfd/generate-from-description   Generate Mermaid from text description
  POST /api/dfd/generate-from-doc           Generate Mermaid from uploaded document
  POST /api/dfd/start-analysis              Start background STRIDE analysis (returns task_id)
  GET  /api/dfd/task/{task_id}/stream       SSE stream of analysis progress steps
  POST /api/dfd/analyze                     Legacy sync analysis (backward compat)
  POST /api/dfd/{dfd_id}/improve            KB-enhanced diagram improvement
  PATCH /api/dfd/{dfd_id}/threat/{idx}/status   Per-threat status update
  GET  /api/dfd/{dfd_id}/export             Export (mmd|original_mmd|json)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.claude.event_bus import drain, publish, subscribe, unsubscribe
from app.config import TEMPLATES_DIR
from app.ingest.path_guard import is_blocked_path
from app.rate_limiter import limiter
from app.storage import dfd_store
from app.storage import documents_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.routers.dfd")

_MAX_DFD_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

@router.get("/dfd")
def dfd_page(request: Request):
    recent = dfd_store.list_recent(limit=10)
    # Show only architecture-category docs and image files — most likely to
    # contain actual diagrams. Runbooks/policies/etc. are excluded.
    all_docs = documents_store.list_documents(limit=100)
    kb_docs = [
        d for d in all_docs
        if d.get("kind") == "image"
        or d.get("category") == "architecture"
        or any(kw in (d.get("source_path") or "").lower()
               for kw in ("dfd", "diagram", "flow", "architect"))
    ][:20]
    return templates.TemplateResponse(
        request=request,
        name="dfd.html",
        context={"recent": recent, "kb_docs": kb_docs},
    )


@router.get("/dfd/from-kb/{doc_id}")
def dfd_from_kb(request: Request, doc_id: str):
    """Bridge page: loads a KB document and pre-stages it for DFD analysis."""
    doc = documents_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return templates.TemplateResponse(
        request=request,
        name="dfd_from_kb.html",
        context={"doc": doc},
    )


@router.get("/api/dfd/kb-doc-bytes/{doc_id}")
def kb_doc_bytes(doc_id: str):
    """Serve the raw bytes of an ingested document.

    Primary: reads from source_path on disk.
    Fallback: reconstructs text from KB chunks stored in the database,
    returned as plain text so the bridge page can submit it to generate-from-doc.
    """
    import mimetypes
    from pathlib import Path
    from fastapi.responses import FileResponse, PlainTextResponse
    from app.db import get_conn

    doc = documents_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try primary: serve from original file on disk
    src = doc.get("source_path", "")
    p = Path(src) if src else None
    if p and p.exists():
        # Re-validate at serve time — the path_guard runs at ingest but this
        # is a defense-in-depth check against DB tampering.
        if is_blocked_path(p.resolve()):
            raise HTTPException(status_code=403, detail="access denied")
        mime, _ = mimetypes.guess_type(str(p))
        return FileResponse(str(p), media_type=mime or "application/octet-stream")

    # Fallback: reassemble from chunks stored in the DB (text docs only)
    if doc.get("kind") == "image":
        raise HTTPException(
            status_code=404,
            detail="Image file is no longer on disk. Re-ingest from the Ingest page to analyze it.",
        )

    conn = get_conn()
    rows = conn.execute(
        "SELECT text_original FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC",
        (doc_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Source file is gone and no text chunks were found. Re-ingest the document.",
        )
    reassembled = "\n\n".join(r["text_original"] or "" for r in rows if r["text_original"])
    return PlainTextResponse(reassembled, media_type="text/plain")


@router.get("/dfd/{dfd_id}")
def dfd_detail(request: Request, dfd_id: str, cached: str = ""):
    record = dfd_store.get(dfd_id)
    if not record:
        raise HTTPException(status_code=404, detail="DFD analysis not found")
    analysis = record.get("analysis", {})
    threats = analysis.get("threats", [])
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    threats_sorted = sorted(
        threats,
        key=lambda t: severity_order.get(t.get("severity", "Low"), 99),
    )

    # Severity summary for summary strip
    sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for t in threats:
        sev = t.get("severity", "Low")
        if sev in sev_counts:
            sev_counts[sev] += 1

    # STRIDE coverage matrix for PDF export
    stride_cats = ["Spoofing", "Tampering", "Repudiation", "Information Disclosure",
                   "Denial of Service", "Elevation of Privilege"]
    sev_levels = ["Critical", "High", "Medium", "Low"]
    stride_matrix = {cat: {sev: 0 for sev in sev_levels} for cat in stride_cats}
    for t in threats:
        cat = t.get("stride_category", "")
        sev = t.get("severity", "Low")
        if cat in stride_matrix and sev in sev_levels:
            stride_matrix[cat][sev] += 1

    from_cache = cached == "1" or record.get("cached", False)

    return templates.TemplateResponse(
        request=request,
        name="dfd_detail.html",
        context={
            "dfd": record,
            "annotated_mermaid": analysis.get("annotated_mermaid", ""),
            "original_mermaid": record.get("mermaid_src", ""),
            "threats": threats_sorted,
            "elements": analysis.get("elements", []),
            "sev_counts": sev_counts,
            "stride_matrix": stride_matrix,
            "stride_cats": stride_cats,
            "sev_levels": sev_levels,
            "from_cache": from_cache,
            "input_format": record.get("input_format") or "mermaid",
        },
    )


# ---------------------------------------------------------------------------
# Generate-from-description
# ---------------------------------------------------------------------------

class GenerateFromDescRequest(BaseModel):
    text: str
    project_id: str | None = None


@router.post("/api/dfd/generate-from-description")
async def generate_from_description(body: GenerateFromDescRequest) -> dict:
    from app.claude import dfd_analyzer

    project_notes = _get_project_notes(body.project_id)
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: dfd_analyzer.generate_from_description(body.text, project_notes=project_notes),
    )
    if not result.mermaid:
        raise HTTPException(status_code=422, detail="; ".join(result.notes) or "Generation failed")
    return {"mermaid": result.mermaid, "notes": result.notes}


# ---------------------------------------------------------------------------
# Generate-from-document
# ---------------------------------------------------------------------------

@router.post("/api/dfd/generate-from-doc")
async def generate_from_doc(
    file: UploadFile = File(...),
    project_id: str = Form(default=""),
) -> dict:
    from app.claude import dfd_analyzer

    file_bytes = await file.read(_MAX_DFD_UPLOAD_BYTES + 1)
    if len(file_bytes) > _MAX_DFD_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (max 20 MB)")
    filename = file.filename or "document.txt"
    project_notes = _get_project_notes(project_id.strip() or None)

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: dfd_analyzer.generate_from_document(
            file_bytes, filename, project_notes=project_notes
        ),
    )
    if not result.mermaid:
        raise HTTPException(status_code=422, detail="; ".join(result.notes) or "Generation failed")
    return {"mermaid": result.mermaid, "notes": result.notes}


# ---------------------------------------------------------------------------
# SSE analysis pipeline
# ---------------------------------------------------------------------------

class StartAnalysisRequest(BaseModel):
    mermaid_src: str = ""
    input_format: str = "mermaid"
    project_id: str | None = None
    force: bool = False


@router.post("/api/dfd/start-analysis")
@limiter.limit("20/hour")
async def start_analysis(request: Request, body: StartAnalysisRequest) -> dict:
    """Start a background STRIDE analysis task. Returns task_id for SSE stream."""
    if not body.mermaid_src.strip():
        raise HTTPException(status_code=400, detail="mermaid_src is required")
    task_id = uuid.uuid4().hex
    asyncio.create_task(_run_analysis_task(task_id, body))
    return {"task_id": task_id}


@router.post("/api/dfd/start-analysis-image")
async def start_analysis_image(
    image: UploadFile = File(...),
    project_id: str = Form(default=""),
    force: bool = Form(default=False),
) -> dict:
    """Start a background image STRIDE analysis task. Returns task_id for SSE stream."""
    image_bytes = await image.read(_MAX_DFD_UPLOAD_BYTES + 1)
    if len(image_bytes) > _MAX_DFD_UPLOAD_BYTES:
        raise HTTPException(413, "image too large (max 20 MB)")
    media_type = image.content_type or "image/png"
    task_id = uuid.uuid4().hex
    asyncio.create_task(_run_image_analysis_task(task_id, image_bytes, media_type,
                                                  project_id.strip() or None, force))
    return {"task_id": task_id}


@router.get("/api/dfd/task/{task_id}/stream")
async def task_stream(task_id: str):
    """SSE stream of analysis step events for a given task_id."""
    topic = f"dfd.{task_id}"
    q = subscribe(topic)

    async def event_source():
        try:
            async for ev in drain(q, idle_timeout=120.0):
                if ev is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {
                    "event": ev.kind,
                    "data": json.dumps(ev.payload, default=str),
                }
                if ev.kind in {"done", "error"}:
                    break
        finally:
            unsubscribe(topic, q)

    return EventSourceResponse(event_source())


async def _run_analysis_task(task_id: str, body: StartAnalysisRequest) -> None:
    """Background task: run STRIDE on Mermaid src and emit SSE step events."""
    from app.claude import dfd_analyzer

    topic = f"dfd.{task_id}"
    try:
        project_notes = _get_project_notes(body.project_id)

        # Step 1: parse/validate input (instant)
        publish(topic, "step", {"step": 1, "status": "complete", "label": "Parsing diagram"})

        # Step 2: before Claude call
        publish(topic, "step", {"step": 2, "status": "active", "label": "Identifying system components"})
        await asyncio.sleep(0)  # yield to event loop

        dfd_id, analysis, from_cache = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: dfd_analyzer.analyze_mermaid(
                body.mermaid_src.strip(),
                force=body.force,
                project_id=body.project_id,
                project_notes=project_notes,
                input_format=body.input_format,
            ),
        )

        # Step 3: elements extracted from Claude response
        publish(topic, "step", {"step": 3, "status": "complete", "label": "Mapping attack surfaces"})

        # Step 4: result stored, done
        publish(topic, "step", {"step": 4, "status": "complete", "label": "Generating threat model"})
        publish(topic, "done", {"dfd_id": dfd_id, "cached": from_cache})

    except Exception as exc:
        log.exception("analysis task %s failed", task_id)
        publish(topic, "error", {"error": str(exc)})


async def _run_image_analysis_task(
    task_id: str,
    image_bytes: bytes,
    media_type: str,
    project_id: str | None,
    force: bool,
) -> None:
    """Background task: run STRIDE on an image and emit SSE step events."""
    from app.claude import dfd_analyzer

    topic = f"dfd.{task_id}"
    try:
        project_notes = _get_project_notes(project_id)

        publish(topic, "step", {"step": 1, "status": "complete", "label": "Parsing diagram"})
        publish(topic, "step", {"step": 2, "status": "active", "label": "Identifying system components"})
        await asyncio.sleep(0)

        dfd_id, analysis, from_cache = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: dfd_analyzer.analyze_image(
                image_bytes, media_type,
                project_id=project_id,
                project_notes=project_notes,
            ),
        )

        publish(topic, "step", {"step": 3, "status": "complete", "label": "Mapping attack surfaces"})
        publish(topic, "step", {"step": 4, "status": "complete", "label": "Generating threat model"})
        publish(topic, "done", {"dfd_id": dfd_id, "cached": from_cache})

    except Exception as exc:
        log.exception("image analysis task %s failed", task_id)
        publish(topic, "error", {"error": str(exc)})


# ---------------------------------------------------------------------------
# Legacy sync analyze endpoint (backward compatibility)
# ---------------------------------------------------------------------------

@router.post("/api/dfd/analyze")
async def analyze_dfd(
    mermaid_src: str = Form(default=""),
    image: UploadFile = File(default=None),
    force: bool = Form(default=False),
    input_format: str = Form(default="mermaid"),
    project_id: str = Form(default=""),
):
    from app.claude import dfd_analyzer

    pid = project_id.strip() or None
    project_notes = _get_project_notes(pid)

    if image and image.filename:
        image_bytes = await image.read(_MAX_DFD_UPLOAD_BYTES + 1)
        if len(image_bytes) > _MAX_DFD_UPLOAD_BYTES:
            raise HTTPException(413, "image too large (max 20 MB)")
        media_type = image.content_type or "image/png"
        dfd_id, _, from_cache = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: dfd_analyzer.analyze_image(
                image_bytes, media_type, project_id=pid, project_notes=project_notes
            ),
        )
    elif mermaid_src.strip():
        src = mermaid_src.strip()
        dfd_id, _, from_cache = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: dfd_analyzer.analyze_mermaid(
                src, force=force, project_id=pid,
                project_notes=project_notes, input_format=input_format,
            ),
        )
    else:
        raise HTTPException(status_code=400, detail="Provide mermaid_src or an image file")

    return JSONResponse({"dfd_id": dfd_id, "cached": from_cache})


# ---------------------------------------------------------------------------
# Improve
# ---------------------------------------------------------------------------

@router.post("/api/dfd/{dfd_id}/improve")
async def improve_dfd(dfd_id: str):
    """Return an improved Mermaid diagram with missing elements filled in from KB."""
    from app.claude import dfd_analyzer
    from app.kb.search import hybrid_search
    from app.claude.caching import build_kb_block

    record = dfd_store.get(dfd_id)
    if not record:
        raise HTTPException(status_code=404, detail="DFD not found")
    mermaid_src = record.get("mermaid_src") or ""
    if not mermaid_src:
        raise HTTPException(status_code=400, detail="No Mermaid source stored for this DFD")

    try:
        hits = hybrid_search("data flow architecture services trust boundary", k=10)
        kb_block = build_kb_block([h.__dict__ for h in hits], [])
        kb_context = kb_block.get("text", "")
    except Exception:
        kb_context = ""

    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: dfd_analyzer.improve_mermaid(mermaid_src, kb_context)
    )
    return JSONResponse({
        "improved_mermaid": result.improved_mermaid,
        "suggestions": result.suggestions,
    })


# ---------------------------------------------------------------------------
# Per-threat status update
# ---------------------------------------------------------------------------

@router.patch("/api/dfd/{dfd_id}/threat/{threat_idx}/status")
def update_threat_status(dfd_id: str, threat_idx: int, body: dict) -> dict:
    """Persist a status change (open/mitigated/accepted) for a specific threat."""
    record = dfd_store.get(dfd_id)
    if not record:
        raise HTTPException(status_code=404, detail="DFD not found")
    status = (body.get("status") or "open").strip()
    if status not in ("open", "mitigated", "accepted"):
        raise HTTPException(status_code=400, detail="status must be open, mitigated, or accepted")
    analysis = record.get("analysis", {})
    threats = analysis.get("threats", [])
    if 0 <= threat_idx < len(threats):
        threats[threat_idx]["status"] = status
        from app.db import LOCK as _LOCK, get_conn as _get_conn
        with _LOCK:
            _get_conn().execute(
                "UPDATE dfd_analyses SET analysis_json = ? WHERE id = ?",
                (json.dumps(analysis), dfd_id),
            )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/api/dfd/{dfd_id}/export")
def export_dfd(dfd_id: str, format: str = "json"):
    record = dfd_store.get(dfd_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    analysis = record.get("analysis", {})

    if format == "mmd":
        mmd = analysis.get("annotated_mermaid") or record.get("mermaid_src") or ""
        return PlainTextResponse(
            mmd,
            headers={"Content-Disposition": f'attachment; filename="{dfd_id}_annotated.mmd"'},
        )

    if format == "original_mmd":
        mmd = record.get("mermaid_src") or ""
        return PlainTextResponse(
            mmd,
            headers={"Content-Disposition": f'attachment; filename="{dfd_id}_original.mmd"'},
        )

    if format == "json":
        threats = analysis.get("threats", [])
        sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for t in threats:
            sev = t.get("severity", "Low").lower()
            if sev in sev_counts:
                sev_counts[sev] += 1

        export_data = {
            "metadata": {
                "dfd_id": dfd_id,
                "analyzed_at": record.get("created_at"),
                "input_format": record.get("input_format") or "mermaid",
                "total_threats": len(threats),
                "severity_summary": sev_counts,
            },
            "elements": analysis.get("elements", []),
            "threats": threats,
        }
        return JSONResponse(
            export_data,
            headers={"Content-Disposition": f'attachment; filename="{dfd_id}.json"'},
        )

    raise HTTPException(status_code=400, detail="format must be mmd, original_mmd, or json")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_project_notes(project_id: str | None) -> str:
    if not project_id:
        return ""
    try:
        from app.storage.projects_store import get_project
        p = get_project(project_id)
        return (p or {}).get("notes", "") or ""
    except Exception:
        return ""
