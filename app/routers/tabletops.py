"""Tabletop exercise endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.claude import tabletop as tabletop_helper
from app.config import TEMPLATES_DIR
from app.storage import tabletops_store

router = APIRouter()
api = APIRouter(prefix="/api/tabletops")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class GenerateRequest(BaseModel):
    service_id: str | None = None
    threat_kind: str | None = Field(default=None, max_length=200)
    scenario_hook: str | None = Field(default=None, max_length=1000)


class LessonsCapture(BaseModel):
    lessons_md: str
    tags: list[str] = []


@api.get("")
async def list_tts() -> dict:
    return {"tabletops": tabletops_store.list_all()}


@api.post("/generate")
async def generate(body: GenerateRequest) -> dict:
    tt_id = tabletop_helper.generate(
        service_id=body.service_id,
        threat_kind=body.threat_kind,
        scenario_hook=body.scenario_hook,
    )
    return {"id": tt_id}


@api.get("/{tt_id}")
async def get_tt(tt_id: str) -> dict:
    tt = tabletops_store.get(tt_id)
    if not tt:
        raise HTTPException(404, "not found")
    return tt


@api.post("/{tt_id}/capture")
async def capture(tt_id: str, body: LessonsCapture) -> dict:
    if not tabletops_store.get(tt_id):
        raise HTTPException(404, "not found")
    lesson_ids = tabletop_helper.capture_lessons(
        tt_id, lessons_md=body.lessons_md, tags=body.tags,
    )
    return {"lesson_ids": lesson_ids}


@api.post("/{tt_id}/generate-runbook")
async def generate_runbook(tt_id: str) -> dict:
    """Generate an IR runbook from this tabletop scenario."""
    tt = tabletops_store.get(tt_id)
    if not tt:
        raise HTTPException(404, "not found")
    from app.claude.ir_runbook import generate as _gen
    rid = _gen(
        service_entity_id=tt.get("scope_service_id"),
        threat_scenario=tt.get("threat_kind") or "General security incident",
        severity="any",
        tabletop_id=tt_id,
    )
    return {"runbook_id": rid}


@router.get("/tabletops", response_class=HTMLResponse)
def page_list(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="tabletops.html",
        context={"tabletops": tabletops_store.list_all()},
    )


@router.get("/tabletops/new", response_class=HTMLResponse)
def page_new(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="tabletop_new.html",
        context={},
    )


@router.get("/tabletops/{tt_id}", response_class=HTMLResponse)
def page_detail(request: Request, tt_id: str):
    tt = tabletops_store.get(tt_id)
    if not tt:
        raise HTTPException(404, "not found")
    return templates.TemplateResponse(
        request=request,
        name="tabletop_detail.html",
        context={"tabletop": tt},
    )


router.include_router(api)
