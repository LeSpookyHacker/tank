"""Threat model endpoints: generate, list, diff."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.claude import threat_modeling
from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.storage import entities_store, threat_models_store

router = APIRouter()
api = APIRouter(prefix="/api/threat-models")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@api.get("")
async def list_latest() -> dict:
    """All latest TMs (one per service)."""
    return {"threat_models": threat_models_store.list_all_latest()}


@api.get("/drift")
async def drift() -> dict:
    """Services whose latest TM is older than current arch."""
    return {"drifted": threat_modeling.find_drift()}


@api.get("/service/{service_id}")
async def for_service(service_id: str) -> dict:
    """All versions of the TM for a service."""
    return {"versions": threat_models_store.list_versions(service_id)}


@api.post("/generate/{service_id}")
@limiter.limit("5/hour")
async def generate(request: Request, service_id: str) -> dict:
    """Generate a new TM (or v1) for the service. Hits Sonnet."""
    svc = entities_store.get_entity(service_id)
    if not svc:
        raise HTTPException(404, "service not found")
    if svc["type"] != "Service":
        raise HTTPException(400, "entity is not a Service")
    tm_id = threat_modeling.generate(service_id)
    return {"id": tm_id}


@api.post("/{tm_id}/confirm")
async def confirm(tm_id: str) -> dict:
    if not threat_models_store.get(tm_id):
        raise HTTPException(404, "not found")
    threat_models_store.confirm(tm_id)
    return {"ok": True}


@router.get("/threat-models", response_class=HTMLResponse)
def page_list(request: Request):
    tms = threat_models_store.list_all_latest()
    drifted = {d["service_entity_id"] for d in threat_modeling.find_drift()}
    return templates.TemplateResponse(
        request=request,
        name="threat_models.html",
        context={"threat_models": tms, "drifted": drifted},
    )


@router.get("/threat-models/{tm_id}", response_class=HTMLResponse)
def page_detail(request: Request, tm_id: str):
    tm = threat_models_store.get(tm_id)
    if not tm:
        raise HTTPException(404, "not found")
    svc = entities_store.get_entity(tm["service_entity_id"])
    versions = threat_models_store.list_versions(tm["service_entity_id"])
    return templates.TemplateResponse(
        request=request,
        name="threat_model_detail.html",
        context={"tm": tm, "service": svc, "versions": versions},
    )


router.include_router(api)
