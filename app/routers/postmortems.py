"""Postmortem authoring endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import postmortem_authoring as pm_helper
from app.config import TEMPLATES_DIR
from app.storage import postmortems_store

router = APIRouter()
api = APIRouter(prefix="/api/postmortems")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class DraftRequest(BaseModel):
    title: str
    freewrite: str
    severity: str | None = None


class FieldsUpdate(BaseModel):
    fields: dict


@api.get("")
async def list_pms(status: str | None = None) -> dict:
    return {"postmortems": postmortems_store.list_by_status(status)}


@api.post("/draft")
async def draft(body: DraftRequest) -> dict:
    pm_id = pm_helper.draft_from_freewrite(
        title=body.title, freewrite=body.freewrite,
        severity=body.severity,
    )
    return {"id": pm_id}


@api.get("/{pm_id}")
async def get_pm(pm_id: str) -> dict:
    pm = postmortems_store.get(pm_id)
    if not pm:
        raise HTTPException(404, "not found")
    return pm


@api.put("/{pm_id}/fields")
async def update_fields(pm_id: str, body: FieldsUpdate) -> dict:
    if not postmortems_store.get(pm_id):
        raise HTTPException(404, "not found")
    from app.claude.postmortem_authoring import _render
    body_md_red = _render(postmortems_store.get(pm_id)["title"], body.fields)
    # Defense-in-depth rehydration for display body
    from app.redact.engine import rehydrate
    from app.redact.store import load_rehydration_map
    body_md = rehydrate(body_md_red, load_rehydration_map())
    postmortems_store.update_fields(
        pm_id, body.fields,
        body_md=body_md, body_md_redacted=body_md_red,
    )
    return {"ok": True}


@api.post("/{pm_id}/publish")
async def publish(pm_id: str) -> dict:
    try:
        return pm_helper.publish(pm_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/postmortems", response_class=HTMLResponse)
def page_list(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="postmortems.html",
        context={"postmortems": postmortems_store.list_by_status(None)},
    )


@router.get("/postmortems/new", response_class=HTMLResponse)
def page_new(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="postmortem_new.html",
        context={},
    )


@router.get("/postmortems/{pm_id}", response_class=HTMLResponse)
def page_detail(request: Request, pm_id: str):
    pm = postmortems_store.get(pm_id)
    if not pm:
        raise HTTPException(404, "not found")
    return templates.TemplateResponse(
        request=request,
        name="postmortem_editor.html",
        context={"pm": pm},
    )


router.include_router(api)
