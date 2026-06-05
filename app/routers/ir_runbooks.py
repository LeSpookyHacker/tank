"""IR runbook endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.storage import entities_store, ir_runbooks_store

log = logging.getLogger("tank.routers.ir_runbooks")

router = APIRouter()
api = APIRouter(prefix="/api/ir-runbooks")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class GenerateRequest(BaseModel):
    service_entity_id: str | None = None
    threat_scenario: str = Field(max_length=2_000)
    severity: str = "any"
    tabletop_id: str | None = None


@api.get("")
async def list_runbooks(service_entity_id: str | None = None) -> dict:
    return {"runbooks": ir_runbooks_store.list_all(
        service_entity_id=service_entity_id,
    )}


@api.post("/generate")
@limiter.limit("5/hour")
async def generate(request: Request, body: GenerateRequest, background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(
        _run_generate,
        service_entity_id=body.service_entity_id,
        threat_scenario=body.threat_scenario,
        severity=body.severity,
        tabletop_id=body.tabletop_id,
    )
    return {"ok": True, "message": "runbook generation queued"}


@api.post("/generate-sync")
@limiter.limit("5/hour")
async def generate_sync(request: Request, body: GenerateRequest) -> dict:
    """Blocking generation — used when the caller needs the runbook_id immediately."""
    from app.claude.ir_runbook import generate as _gen
    rid = _gen(
        service_entity_id=body.service_entity_id,
        threat_scenario=body.threat_scenario,
        severity=body.severity,
        tabletop_id=body.tabletop_id,
    )
    return {"runbook_id": rid}


@api.get("/{runbook_id}")
async def get_runbook(runbook_id: str) -> dict:
    rb = ir_runbooks_store.get(runbook_id)
    if not rb:
        raise HTTPException(404, "not found")
    return rb


@api.post("/{runbook_id}/confirm")
async def confirm(runbook_id: str) -> dict:
    if not ir_runbooks_store.get(runbook_id):
        raise HTTPException(404, "not found")
    ir_runbooks_store.confirm(runbook_id)
    return {"ok": True}


@api.delete("/{runbook_id}")
async def delete_runbook(runbook_id: str) -> dict:
    if not ir_runbooks_store.get(runbook_id):
        raise HTTPException(404, "not found")
    ir_runbooks_store.delete(runbook_id)
    return {"ok": True}


def _run_generate(
    *,
    service_entity_id: str | None,
    threat_scenario: str,
    severity: str,
    tabletop_id: str | None,
) -> None:
    try:
        from app.claude.ir_runbook import generate as _gen
        _gen(
            service_entity_id=service_entity_id,
            threat_scenario=threat_scenario,
            severity=severity,
            tabletop_id=tabletop_id,
        )
    except Exception as exc:
        log.warning("background runbook generation failed: %s", exc)


# ── HTML pages ──────────────────────────────────────────────────────

@router.get("/ir-runbooks", response_class=HTMLResponse)
def page_list(request: Request, service_entity_id: str | None = None):
    runbooks = ir_runbooks_store.list_all(service_entity_id=service_entity_id)

    # Attach service names.
    for rb in runbooks:
        if rb.get("service_entity_id"):
            ent = entities_store.get_entity(rb["service_entity_id"])
            rb["service_name"] = ent["name"] if ent else None
        else:
            rb["service_name"] = None

    # Build service list for the generate form.
    services = entities_store.list_entities(type_="Service", limit=100)

    return templates.TemplateResponse(
        request=request,
        name="ir_runbooks.html",
        context={
            "runbooks": runbooks,
            "services": services,
            "filter_service_id": service_entity_id,
        },
    )


@router.get("/ir-runbooks/{runbook_id}", response_class=HTMLResponse)
def page_detail(request: Request, runbook_id: str):
    rb = ir_runbooks_store.get(runbook_id)
    if not rb:
        raise HTTPException(404, "not found")

    service_name = None
    if rb.get("service_entity_id"):
        ent = entities_store.get_entity(rb["service_entity_id"])
        service_name = ent["name"] if ent else None

    return templates.TemplateResponse(
        request=request,
        name="ir_runbook_detail.html",
        context={"runbook": rb, "service_name": service_name},
    )


router.include_router(api)
