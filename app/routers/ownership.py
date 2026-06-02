"""Service ownership + on-call / escalation roster.

Answers "who operates this service, who's on-call, who do I escalate to?"
Distinct from `/me` (the user's personal ownership claims). Reuses
`me._risk_score_for` for the per-service risk badge.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.routers.me import _risk_score_for
from app.storage import entities_store, ownership_store

router = APIRouter()
api = APIRouter(prefix="/api/ownership")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _person_label(entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    ent = entities_store.get_entity(entity_id)
    return ent["name"] if ent else None


class EscalationLevel(BaseModel):
    level: str
    contact: str


class OwnershipPayload(BaseModel):
    entity_id: str
    primary_owner_entity_id: str | None = None
    secondary_owner_entity_id: str | None = None
    on_call_contact: str | None = None
    escalation: list[EscalationLevel] = []
    slack_channel: str | None = None
    pager_handle: str | None = None


@router.get("/ownership", response_class=HTMLResponse)
def ownership_page(request: Request):
    services = entities_store.list_entities(type_="Service", limit=500)
    people = entities_store.list_entities(type_="Person", limit=500)
    rows = []
    for svc in services:
        own = ownership_store.get(svc["id"]) or ownership_store.seed_from_graph(svc["id"])
        rows.append({
            "service": svc,
            "ownership": own,
            "primary_label": _person_label(own["primary_owner_entity_id"]) if own else None,
            "secondary_label": _person_label(own["secondary_owner_entity_id"]) if own else None,
            "risk_score": _risk_score_for(svc["id"]),
        })
    rows.sort(key=lambda r: r["risk_score"], reverse=True)
    return templates.TemplateResponse(
        request=request, name="ownership.html",
        context={"state": get_state(), "rows": rows, "people": people},
    )


@api.post("")
async def set_ownership(body: OwnershipPayload) -> dict:
    svc = entities_store.get_entity(body.entity_id)
    if not svc:
        raise HTTPException(404, "no such entity")
    ownership_store.set_owner(
        entity_id=body.entity_id,
        primary_owner_entity_id=body.primary_owner_entity_id or None,
        secondary_owner_entity_id=body.secondary_owner_entity_id or None,
        on_call_contact=body.on_call_contact or None,
        escalation=[e.model_dump() for e in body.escalation],
        slack_channel=body.slack_channel or None,
        pager_handle=body.pager_handle or None,
        provenance="user",
    )
    return {"ok": True}


@api.get("/{entity_id}")
async def get_ownership(entity_id: str) -> dict:
    own = ownership_store.get(entity_id)
    if not own:
        return {"ownership": None}
    own["primary_label"] = _person_label(own["primary_owner_entity_id"])
    own["secondary_label"] = _person_label(own["secondary_owner_entity_id"])
    return {"ownership": own}


@api.delete("/{entity_id}")
async def clear_ownership(entity_id: str) -> dict:
    ownership_store.clear(entity_id)
    return {"ok": True}


router.include_router(api)
