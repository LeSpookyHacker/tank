"""Risk register + vulnerability intake endpoints."""
from __future__ import annotations

import logging
import os
import secrets as _secrets
import time

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.redact.engine import apply_redactions
from app.schemas import VulnerabilityIntake
from app.storage import risks_store, vulnerabilities_store
from app.storage import entities_store

log = logging.getLogger("tank.routers.risks")

router = APIRouter()
api = APIRouter(prefix="/api/risks")
vuln_api = APIRouter(prefix="/api/vulnerabilities")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Risk register CRUD ──────────────────────────────────────────────

class CreateRisk(BaseModel):
    title: str = Field(max_length=500)
    description: str = Field(max_length=50_000)
    category: str = "other"
    inherent_likelihood: int = 3
    inherent_impact: int = 3
    treatment: str = "mitigate"
    treatment_rationale: str | None = Field(None, max_length=10_000)
    owner_entity_id: str | None = None
    scope_entity_ids: list[str] = []
    controls: list[str] = Field(default_factory=list, max_length=50)
    review_days: int = 90


class UpdateStatus(BaseModel):
    status: str
    closure_rationale: str | None = None


@api.get("")
async def list_risks(
    status: str | None = "open",
    category: str | None = None,
) -> dict:
    return {"risks": risks_store.list_all(status=status, category=category)}


@api.get("/{risk_id}")
async def get_risk(risk_id: str) -> dict:
    r = risks_store.get(risk_id)
    if not r:
        raise HTTPException(404, "not found")
    return r


@api.post("")
async def create_risk(body: CreateRisk, background_tasks: BackgroundTasks) -> dict:
    review_at = int(time.time()) + body.review_days * 86400
    # Redact description before storing.
    desc_redacted = apply_redactions(body.description).redacted_text
    rid = risks_store.create(
        title=body.title,
        description=desc_redacted,
        category=body.category,
        inherent_likelihood=body.inherent_likelihood,
        inherent_impact=body.inherent_impact,
        treatment=body.treatment,
        treatment_rationale=body.treatment_rationale,
        owner_entity_id=body.owner_entity_id,
        scope_entity_ids=body.scope_entity_ids,
        controls=body.controls,
        review_at=review_at,
    )
    # Kick off async assessment.
    background_tasks.add_task(_run_assessment, rid)
    return {"id": rid}


@api.post("/{risk_id}/assess")
@limiter.limit("20/hour")
async def assess_risk(request: Request, risk_id: str, background_tasks: BackgroundTasks) -> dict:
    if not risks_store.get(risk_id):
        raise HTTPException(404, "not found")
    background_tasks.add_task(_run_assessment, risk_id)
    return {"ok": True, "message": "assessment queued"}


@api.put("/{risk_id}/status")
async def update_status(risk_id: str, body: UpdateStatus) -> dict:
    if not risks_store.get(risk_id):
        raise HTTPException(404, "not found")
    risks_store.set_status(risk_id, body.status, body.closure_rationale)
    return {"ok": True}


def _run_assessment(risk_id: str) -> None:
    try:
        from app.claude.risk_register import assess
        assess(risk_id)
    except Exception as exc:
        log.warning("background assessment for risk %s failed: %s", risk_id, exc)


# ── Vulnerability intake (for Nyx and other tools) ─────────────────

_NYX_KEY = os.environ.get("TANK_NYX_API_KEY", "")


@vuln_api.post("/intake")
async def intake_vulnerability(
    body: VulnerabilityIntake,
    x_nyx_key: str = Header(default=""),
) -> dict:
    """Accept a vulnerability finding from an external tool (e.g. Nyx).

    Tank redacts the description, looks up service entity IDs by name,
    and creates a `vulnerabilities` row. Returns the new vuln_id.
    """
    if not _NYX_KEY:
        raise HTTPException(503, "vulnerability intake not configured (set TANK_NYX_API_KEY)")
    if not _secrets.compare_digest(x_nyx_key, _NYX_KEY):
        raise HTTPException(401, "invalid API key")
    # Resolve service names → entity IDs.
    affected_ids: list[str] = []
    for name in body.affected_service_names:
        from app.kb.entities import find_by_name
        card = find_by_name("Service", name)
        if card:
            affected_ids.append(card["id"])

    desc_redacted: str | None = None
    if body.description:
        desc_redacted = apply_redactions(body.description).redacted_text

    vid = vulnerabilities_store.create(
        title=body.title,
        description=desc_redacted,
        cve_id=body.cve_id,
        cvss_score=body.cvss_score,
        cvss_vector=body.cvss_vector,
        severity=body.severity,
        source=body.source,
        affected_service_ids=affected_ids,
        due_at=body.due_at,
        external_ref=body.external_ref,
    )
    return {"vuln_id": vid}


@vuln_api.get("")
async def list_vulns(
    severity: str | None = None,
    source: str | None = None,
) -> dict:
    return {"vulnerabilities": vulnerabilities_store.list_open(
        severity=severity, source=source,
    )}


# ── Risk register page ──────────────────────────────────────────────

@router.get("/risks", response_class=HTMLResponse)
def page_risks(
    request: Request,
    status: str = "open",
    category: str | None = None,
) -> HTMLResponse:
    risks = risks_store.list_all(status=status, category=category)
    overdue = risks_store.review_overdue()
    counts = risks_store.counts_by_status()

    # Attach owner names.
    for r in risks:
        if r.get("owner_entity_id"):
            ent = entities_store.get_entity(r["owner_entity_id"])
            r["owner_name"] = ent["name"] if ent else None
        else:
            r["owner_name"] = None

    return templates.TemplateResponse(
        request=request,
        name="risks.html",
        context={
            "risks": risks,
            "overdue_count": len(overdue),
            "counts": counts,
            "status": status,
            "category": category,
            "now_ts": int(time.time()),
            "categories": [
                "data_breach", "availability", "supply_chain",
                "access_control", "regulatory", "ai_model_abuse",
                "insider_threat", "third_party", "infrastructure",
                "application", "other",
            ],
        },
    )


@router.get("/risks/{risk_id}", response_class=HTMLResponse)
def page_risk_detail(request: Request, risk_id: str) -> HTMLResponse:
    r = risks_store.get(risk_id)
    if not r:
        raise HTTPException(404, "not found")

    owner_name = None
    if r.get("owner_entity_id"):
        ent = entities_store.get_entity(r["owner_entity_id"])
        owner_name = ent["name"] if ent else None

    scope_entities = []
    for eid in (r.get("scope_entity_ids") or []):
        ent = entities_store.get_entity(eid)
        if ent:
            scope_entities.append(ent)

    return templates.TemplateResponse(
        request=request,
        name="risk_detail.html",
        context={
            "risk": r,
            "owner_name": owner_name,
            "scope_entities": scope_entities,
        },
    )


router.include_router(api)
router.include_router(vuln_api)
