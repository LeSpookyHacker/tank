"""Lessons-learned DB endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.storage import lessons_store

router = APIRouter()
api = APIRouter(prefix="/api/lessons")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateLesson(BaseModel):
    title: str
    body_md: str
    source_kind: str = "user"
    source_id: str = ""
    tags: list[str] = []
    scope_entity_ids: list[str] = []


@api.get("")
async def list_recent(
    days: int = Query(default=365, ge=1, le=1825),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"lessons": lessons_store.list_recent(days=days, limit=limit)}


@api.get("/search")
async def search(q: str, tag: str | None = None,
                 limit: int = Query(default=25, ge=1, le=200)) -> dict:
    return {"lessons": lessons_store.search(q, tag=tag, limit=limit)}


@api.get("/tag/{tag}")
async def by_tag(tag: str,
                 limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"lessons": lessons_store.list_by_tag(tag, limit=limit)}


@api.get("/{lesson_id}")
async def get_one(lesson_id: str) -> dict:
    lesson = lessons_store.get(lesson_id)
    if not lesson:
        raise HTTPException(404, "not found")
    return lesson


@api.post("")
async def create(body: CreateLesson) -> dict:
    lid = lessons_store.create(
        title=body.title, body_md=body.body_md,
        source_kind=body.source_kind, source_id=body.source_id,
        tags=body.tags, scope_entity_ids=body.scope_entity_ids,
    )
    return {"id": lid}


@router.get("/lessons", response_class=HTMLResponse)
def page(request: Request, q: str | None = None, tag: str | None = None):
    if q:
        rows = lessons_store.search(q, tag=tag, limit=50)
    elif tag:
        rows = lessons_store.list_by_tag(tag, limit=50)
    else:
        rows = lessons_store.list_recent(days=365, limit=100)
    return templates.TemplateResponse(
        request=request,
        name="lessons.html",
        context={"lessons": rows, "q": q, "tag": tag},
    )


router.include_router(api)
