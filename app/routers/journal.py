"""Journal endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.claude.journal_extractor import submit
from app.config import TEMPLATES_DIR
from app.redact.engine import apply_redactions
from app.role import get_state, tenure_day
from app.storage import journal_store

router = APIRouter(prefix="/api/journal")

# Page router (no prefix) — wired separately in app/main.py.
page = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class JournalIn(BaseModel):
    body: str = Field(max_length=100_000)
    title: str | None = Field(None, max_length=500)


class JournalUpdateIn(BaseModel):
    body: str = Field(max_length=100_000)
    title: str | None = Field(None, max_length=500)


@page.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request):
    today = journal_store.get_today()
    return templates.TemplateResponse(
        request=request, name="journal.html",
        context={
            "state": get_state(),
            "tenure": tenure_day(),
            "today": today,
            "today_id": today["id"] if today else None,
            "recent": journal_store.list_recent(90),
        },
    )


@page.get("/journal/today", response_class=HTMLResponse)
async def journal_today_page(request: Request):
    today = journal_store.get_today()
    if today:
        return RedirectResponse(f"/journal/{today['id']}", status_code=302)
    return templates.TemplateResponse(
        request=request, name="journal_entry.html",
        context={
            "entry": None,
            "is_today": True,
            "tenure": tenure_day(),
        },
    )


@page.get("/journal/{entry_id}", response_class=HTMLResponse)
async def journal_entry_page(request: Request, entry_id: str):
    entry = journal_store.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    today = journal_store.get_today()
    return templates.TemplateResponse(
        request=request, name="journal_entry.html",
        context={
            "entry": entry,
            "is_today": today is not None and today["id"] == entry_id,
            "tenure": tenure_day(),
        },
    )


@router.post("")
async def post_journal(body: JournalIn) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: submit(body.body, body.title),
    )


@router.put("/{entry_id}")
async def put_journal(entry_id: str, body: JournalUpdateIn) -> dict:
    """Update an existing entry by ID; re-runs extraction."""
    entry = journal_store.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    loop = asyncio.get_event_loop()

    def _update():
        redacted = apply_redactions(body.body)
        journal_store.update_by_id(
            entry_id,
            body=body.body,
            body_redacted=redacted.redacted_text,
            title=body.title,
        )
        # Re-run extraction so follow-up nudges stay fresh.
        from app.claude.journal_extractor import _extract
        diff = _extract(redacted.redacted_text)
        journal_store.set_extracted(
            entry_id,
            diff.model_dump() if hasattr(diff, "model_dump") else diff,
        )
        return {"journal_id": entry_id,
                "diff": diff.model_dump() if hasattr(diff, "model_dump") else diff}

    return await loop.run_in_executor(None, _update)


@router.get("/today")
async def get_today() -> dict:
    return journal_store.get_today() or {"entry": None}


@router.get("/recent")
async def get_recent(days: int = Query(default=14, ge=1, le=365)) -> dict:
    return {"entries": journal_store.list_recent(days)}


@router.get("/week")
async def get_week() -> dict:
    return {"entries": journal_store.for_week()}
