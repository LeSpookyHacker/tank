"""Tabletop exercise endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import tabletop as tabletop_helper
from app.config import TEMPLATES_DIR
from app.storage import tabletops_store

router = APIRouter()
api = APIRouter(prefix="/api/tabletops")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class GenerateRequest(BaseModel):
    service_id: str | None = None
    threat_kind: str | None = None
    scenario_hook: str | None = None


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
