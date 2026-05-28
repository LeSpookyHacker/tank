"""Security Stack Audit — structured inventory of 15 capability categories.

Routes:
  GET  /stack-audit            — serve the stack audit page
  POST /api/stack-audit/save   — save one or more category assessments
  GET  /api/stack-audit        — return all 15 categories with current state
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import asset_inventory_store as inv_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class SaveCategoryBody(BaseModel):
    capability_category: str
    tool_name: str | None = None
    deployment_status: str = "none"
    coverage_notes: str | None = None
    known_gaps: str | None = None


@router.get("/stack-audit", response_class=HTMLResponse)
def stack_audit_page(request: Request):
    state = get_state()
    categories = inv_store.get_all()
    completion_pct = inv_store.completion_percentage()
    return templates.TemplateResponse(
        request=request,
        name="stack_audit.html",
        context={
            "state": state,
            "categories": categories,
            "completion_pct": completion_pct,
        },
    )


@router.get("/api/stack-audit")
def get_stack_audit() -> JSONResponse:
    return JSONResponse({
        "categories": inv_store.get_all(),
        "completion_pct": inv_store.completion_percentage(),
    })


@router.post("/api/stack-audit/save")
def save_category(body: SaveCategoryBody) -> JSONResponse:
    if body.capability_category not in inv_store.CAPABILITY_CATEGORIES:
        return JSONResponse({"error": "Unknown category"}, status_code=422)
    iid = inv_store.upsert(
        capability_category=body.capability_category,
        tool_name=body.tool_name or None,
        deployment_status=body.deployment_status,
        coverage_notes=body.coverage_notes or None,
        known_gaps=body.known_gaps or None,
    )
    return JSONResponse({
        "ok": True,
        "id": iid,
        "completion_pct": inv_store.completion_percentage(),
    })
