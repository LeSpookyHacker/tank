"""Glossary endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import glossary_extractor
from app.config import TEMPLATES_DIR
from app.storage import glossary_store

router = APIRouter()
api = APIRouter(prefix="/api/glossary")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class TermPayload(BaseModel):
    term: str
    definition: str
    aliases: list[str] = []


@api.get("")
async def list_all() -> dict:
    return {
        "confirmed": glossary_store.list_confirmed(),
        "pending": glossary_store.list_pending(),
    }


@api.post("/discover")
async def discover() -> dict:
    ids = glossary_extractor.discover()
    return {"new_pending_ids": ids}


@api.post("/{term_id}/confirm")
async def confirm(term_id: str) -> dict:
    if not glossary_store.get(term_id):
        raise HTTPException(404, "not found")
    glossary_store.confirm(term_id)
    return {"ok": True}


@api.post("/{term_id}/reject")
async def reject(term_id: str) -> dict:
    if not glossary_store.get(term_id):
        raise HTTPException(404, "not found")
    glossary_store.reject(term_id)
    return {"ok": True}


@api.post("")
async def manual_add(body: TermPayload) -> dict:
    gid = glossary_store.upsert(
        term=body.term, definition=body.definition,
        aliases=body.aliases, confirmed=True,
    )
    return {"id": gid}


@router.get("/glossary", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="glossary.html",
        context={
            "confirmed": glossary_store.list_confirmed(),
            "pending": glossary_store.list_pending(),
        },
    )


router.include_router(api)
