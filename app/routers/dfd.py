"""DFD threat modeling endpoints."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.storage import dfd_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.routers.dfd")


@router.get("/dfd")
def dfd_page(request: Request):
    recent = dfd_store.list_recent(limit=10)
    return templates.TemplateResponse(
        request=request,
        name="dfd.html",
        context={"recent": recent},
    )


@router.get("/dfd/{dfd_id}")
def dfd_detail(request: Request, dfd_id: str):
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
    return templates.TemplateResponse(
        request=request,
        name="dfd_detail.html",
        context={
            "dfd": record,
            "annotated_mermaid": analysis.get("annotated_mermaid", ""),
            "threats": threats_sorted,
            "elements": analysis.get("elements", []),
        },
    )


@router.post("/api/dfd/analyze")
async def analyze_dfd(
    mermaid_src: str = Form(default=""),
    image: UploadFile = File(default=None),
    force: bool = Form(default=False),
):
    from app.claude import dfd_analyzer

    if image and image.filename:
        image_bytes = await image.read()
        media_type = image.content_type or "image/png"
        dfd_id, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: dfd_analyzer.analyze_image(image_bytes, media_type)
        )
    elif mermaid_src.strip():
        src = mermaid_src.strip()
        dfd_id, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: dfd_analyzer.analyze_mermaid(src, force=force)
        )
    else:
        raise HTTPException(status_code=400, detail="Provide mermaid_src or an image file")

    return JSONResponse({"dfd_id": dfd_id})


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

    # Retrieve relevant KB chunks using the existing diagram as the query
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
            headers={"Content-Disposition": f'attachment; filename="{dfd_id}.mmd"'},
        )
    if format == "json":
        return JSONResponse(
            analysis,
            headers={"Content-Disposition": f'attachment; filename="{dfd_id}.json"'},
        )
    raise HTTPException(status_code=400, detail="format must be mmd or json")
