"""Entity browser + graph API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.kb import entities as kb_entities
from app.kb import relationships as kb_relationships
from app.role import get_state
from app.storage import entities_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------- HTML ----------------

@router.get("/entities", response_class=HTMLResponse)
async def entities_page(request: Request, type: str | None = None):
    state = get_state()
    counts = entities_store.count_by_type()
    if not type and counts:
        first = sorted(counts.keys())[0]
        return RedirectResponse(f"/entities?type={first}")
    ents = kb_entities.list_by_type(type, limit=200) if type else []
    return templates.TemplateResponse(
        request=request, name="entities.html",
        context={"state": state, "counts": counts,
                 "selected_type": type, "entities": ents},
    )


@router.get("/entities/{entity_id}", response_class=HTMLResponse)
async def entity_detail(request: Request, entity_id: str):
    card = kb_entities.get_card(entity_id)
    if not card:
        raise HTTPException(404, "no such entity")
    edges = kb_relationships.traverse(entity_id, direction="both")
    state = get_state()
    return templates.TemplateResponse(
        request=request, name="entity_detail.html",
        context={"state": state, "card": card, "graph": edges},
    )


# ---------------- API ----------------

@router.get("/api/entities")
async def list_entities(
    type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    return {
        "counts": entities_store.count_by_type(),
        "entities": kb_entities.list_by_type(type, limit=limit) if type else [],
    }


@router.get("/api/entities/{entity_id}")
async def get_entity(entity_id: str) -> dict:
    card = kb_entities.get_card(entity_id)
    if not card:
        raise HTTPException(404, "no such entity")
    return card


@router.get("/api/entities/{entity_id}/graph")
async def entity_graph(
    entity_id: str,
    hops: int = Query(default=1, ge=1, le=5),
) -> dict:
    return kb_relationships.traverse(entity_id, hops=hops)


@router.get("/api/entities-graph")
async def graph_overview(
    type: str = "Service",
    depth: int = Query(default=2, ge=1, le=5),
) -> dict:
    return kb_relationships.graph_for_type(type, depth=depth)
