"""Follow-up endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage import followups_store

router = APIRouter(prefix="/api/followups")


class CreateFollowup(BaseModel):
    title: str
    body: str | None = None
    source_kind: str = "user"
    source_id: str | None = None
    related_entity_id: str | None = None
    due_at: float | None = None


@router.get("")
async def list_followups(status: str = "open") -> dict:
    return {"followups": followups_store.list_by_status(status)}


@router.get("/due-today")
async def due_today() -> dict:
    return {"followups": followups_store.list_due_today()}


@router.post("")
async def create_followup(body: CreateFollowup) -> dict:
    fid = followups_store.create(
        title=body.title, body=body.body,
        source_kind=body.source_kind, source_id=body.source_id,
        related_entity_id=body.related_entity_id,
        due_at=body.due_at,
    )
    return {"id": fid}


@router.post("/{followup_id}/done")
async def mark_done(followup_id: str) -> dict:
    followups_store.set_status(followup_id, "done")
    return {"ok": True}


@router.post("/{followup_id}/cancel")
async def cancel(followup_id: str) -> dict:
    followups_store.set_status(followup_id, "cancelled")
    return {"ok": True}


@router.post("/{followup_id}/snooze")
async def snooze(followup_id: str) -> dict:
    followups_store.set_status(followup_id, "snoozed")
    return {"ok": True}
