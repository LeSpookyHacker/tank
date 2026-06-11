"""Detection coverage endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.kb import detections as detections_kb
from app.storage import entities_store

router = APIRouter()
api = APIRouter(prefix="/api/detections")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@api.get("")
async def list_detections() -> dict:
    return {"detections": entities_store.list_entities(
        type_="Detection", limit=200,
    )}


@api.get("/for-technique/{attack_id}")
async def for_technique(attack_id: str) -> dict:
    return detections_kb.find_for_technique(attack_id)


@api.get("/coverage")
async def coverage() -> dict:
    return {"rows": detections_kb.coverage_table(limit_services=20)}


@router.get("/detections", response_class=HTMLResponse)
def page_list(request: Request):
    detections = entities_store.list_entities(type_="Detection", limit=200)
    techniques = entities_store.list_entities(
        type_="AttackTechnique", limit=200,
    )
    return templates.TemplateResponse(
        request=request,
        name="detections.html",
        context={"detections": detections, "techniques": techniques},
    )


@router.get("/coverage-map", response_class=HTMLResponse)
def coverage_map_page(request: Request):
    data = detections_kb.coverage_by_technique()
    detection_count = len(
        entities_store.list_entities(type_="Detection", limit=500)
    )
    return templates.TemplateResponse(
        request=request,
        name="coverage_map.html",
        context={**data, "detection_count": detection_count},
    )


router.include_router(api)
