"""Personal ownership dashboard."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import threat_modeling
from app.config import TEMPLATES_DIR
from app.storage import (decisions_store, entities_store, followups_store,
                         owned_store, postmortems_store, threat_models_store)

router = APIRouter()
api = APIRouter(prefix="/api/me")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ClaimPayload(BaseModel):
    entity_id: str
    role: str = "owner"


def _risk_score_for(entity_id: str) -> float:
    """Coarse 0-10 risk score for an owned entity.

    Heuristic, not gospel: penalize TM drift, unaddressed high/high
    threats, expired decisions in scope, and open postmortem action
    items affecting the entity.
    """
    score = 0.0
    # TM drift / missing
    tm = threat_models_store.latest_for_service(entity_id)
    if not tm:
        score += 3.0
    else:
        try:
            current = threat_modeling.current_arch_hash(entity_id)
            if current != tm["arch_snapshot_hash"]:
                score += 2.0
        except Exception:
            pass
        for t in (tm.get("threats") or []):
            if t.get("likelihood") == "high" and t.get("impact") == "high":
                if not t.get("suggested_controls"):
                    score += 1.5
                    break

    # Decisions in scope
    decisions = decisions_store.list_filtered(scope_entity_id=entity_id)
    now = time.time()
    for d in decisions:
        if d.get("expires_at") and d["expires_at"] < now:
            score += 0.7

    # Open postmortem followups that reference this entity (any in
    # services_affected)
    open_fus = followups_store.list_by_status("open", limit=200)
    for f in open_fus:
        if f.get("related_entity_id") == entity_id:
            score += 0.5

    return min(score, 10.0)


@api.get("/owned")
async def list_owned_entities() -> dict:
    owned = owned_store.list_owned()
    enriched = []
    for o in owned:
        ent = entities_store.get_entity(o["entity_id"])
        if not ent:
            continue
        enriched.append({
            "entity": ent,
            "role": o["role"],
            "risk_score": _risk_score_for(o["entity_id"]),
        })
    enriched.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"owned": enriched}


@api.post("/owned")
async def claim(body: ClaimPayload) -> dict:
    if not entities_store.get_entity(body.entity_id):
        raise HTTPException(404, "entity not found")
    owned_store.claim(entity_id=body.entity_id, role=body.role)
    return {"ok": True}


@api.delete("/owned/{entity_id}")
async def release(entity_id: str) -> dict:
    owned_store.release(entity_id=entity_id)
    return {"ok": True}


@router.get("/me", response_class=HTMLResponse)
def page(request: Request):
    owned = owned_store.list_owned()
    enriched = []
    for o in owned:
        ent = entities_store.get_entity(o["entity_id"])
        if not ent:
            continue
        enriched.append({
            "entity": ent,
            "role": o["role"],
            "risk_score": _risk_score_for(o["entity_id"]),
        })
    enriched.sort(key=lambda x: x["risk_score"], reverse=True)
    return templates.TemplateResponse(
        request=request,
        name="me.html",
        context={"owned": enriched},
    )


router.include_router(api)
