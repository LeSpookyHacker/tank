"""Journal endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.claude.journal_extractor import submit
from app.storage import journal_store

router = APIRouter(prefix="/api/journal")


class JournalIn(BaseModel):
    body: str


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
async def get_recent(days: int = 14) -> dict:
    return {"entries": journal_store.list_recent(days)}


@router.get("/week")
async def get_week() -> dict:
    return {"entries": journal_store.for_week()}
