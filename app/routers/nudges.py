"""Nudge endpoints."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Query

from app.claude.nudges import generate_nudges
from app.storage import nudges_store

router = APIRouter(prefix="/api/nudges")


@router.get("/today")
async def list_today() -> dict:
    return {"nudges": nudges_store.list_open()}


@router.post("/regenerate")
async def regenerate() -> dict:
    loop = asyncio.get_event_loop()
    ids = await loop.run_in_executor(None, generate_nudges)
    return {"created": ids}


@router.post("/{nudge_id}/dismiss")
async def dismiss(nudge_id: str) -> dict:
    nudges_store.set_status(nudge_id, "dismissed")
    return {"ok": True}


@router.post("/{nudge_id}/act")
async def act(nudge_id: str) -> dict:
    nudges_store.set_status(nudge_id, "acted")
    return {"ok": True}


@router.post("/{nudge_id}/snooze")
async def snooze(nudge_id: str,
                 hours: int = Query(default=24, ge=1, le=8760)) -> dict:
    nudges_store.snooze(nudge_id, time.time() + hours * 3600)
    return {"ok": True}
