"""Notes (learning-capture) endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude.notes import commit_diff, create_note
from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import notes_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateNote(BaseModel):
    body: str
    meeting_with_entity_id: str | None = None


class ConfirmNote(BaseModel):
    entities: list[int] = []
    relationships: list[int] = []


@router.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    state = get_state()
    recent = notes_store.list_recent(20)
    return templates.TemplateResponse(
        request=request, name="notes.html",
        context={"state": state, "notes": recent},
    )


@router.post("/api/notes")
async def post_note(body: CreateNote) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: create_note(
            body=body.body,
            meeting_with_entity_id=body.meeting_with_entity_id,
        ),
    )


@router.post("/api/notes/{note_id}/confirm")
async def confirm_note(note_id: str, body: ConfirmNote) -> dict:
    accept = {
        "entities": body.entities,
        "relationships": body.relationships,
    }
    return commit_diff(note_id=note_id, accept=accept)


@router.get("/api/notes/{note_id}")
async def get_note(note_id: str) -> dict:
    n = notes_store.get(note_id)
    if not n:
        raise HTTPException(404, "no such note")
    return n
