"""Report-subscription endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.role import get_state
from app.storage import subscriptions_store

router = APIRouter(prefix="/api/subscriptions")


class CreateSubscription(BaseModel):
    kind: str
    cadence: str   # daily|weekly|monthly|quarterly
    scope: dict | None = None


@router.get("")
async def list_subs() -> dict:
    return {"subscriptions": subscriptions_store.list_all()}


@router.post("")
async def subscribe(body: CreateSubscription) -> dict:
    state = get_state()
    try:
        sid = subscriptions_store.subscribe(
            kind=body.kind, cadence=body.cadence,
            role_mode=state.role_mode.value, scope=body.scope,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"id": sid}


@router.post("/{subscription_id}/disable")
async def disable(subscription_id: str) -> dict:
    subscriptions_store.set_enabled(subscription_id, False)
    return {"ok": True}


@router.post("/{subscription_id}/enable")
async def enable(subscription_id: str) -> dict:
    subscriptions_store.set_enabled(subscription_id, True)
    return {"ok": True}


@router.delete("/{subscription_id}")
async def delete_sub(subscription_id: str) -> dict:
    subscriptions_store.delete(subscription_id)
    return {"ok": True}
