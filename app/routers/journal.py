"""Journal endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude.journal_extractor import submit
from app.config import TEMPLATES_DIR
from app.role import get_state, tenure_day
from app.storage import journal_store

router = APIRouter(prefix="/api/journal")

# Page router (no prefix) — wired separately in app/main.py.
page = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class JournalIn(BaseModel):
    body: str


@page.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="journal.html",
        context={
            "state": get_state(),
            "tenure": tenure_day(),
            "today": journal_store.get_today(),
            "recent": journal_store.list_recent(30),
        },
    )


@router.post("")
async def post_journal(body: JournalIn) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: submit(body.body),
    )


@router.get("/today")
async def get_today() -> dict:
    return journal_store.get_today() or {"entry": None}


@router.get("/recent")
async def get_recent(days: int = Query(default=14, ge=1, le=365)) -> dict:
    return {"entries": journal_store.list_recent(days)}


@router.get("/week")
async def get_week() -> dict:
    return {"entries": journal_store.for_week()}
