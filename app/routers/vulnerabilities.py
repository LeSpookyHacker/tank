"""Vulnerability triage workflow.

Routes:
  GET  /vulnerabilities                  — triage queue view
  POST /api/vulnerabilities/{id}/triage  — triage (set severity, notes)
  POST /api/vulnerabilities/{id}/assign  — assign to owner + due date
  POST /api/vulnerabilities/{id}/close   — close (patched/accepted/wont_fix)
  POST /api/vulnerabilities/{id}/promote — promote to risk register
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import vulnerabilities_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class TriageBody(BaseModel):
    severity: str | None = None
    notes: str | None = None


class AssignBody(BaseModel):
    assigned_to: str
    due_at: int | None = None


class CloseBody(BaseModel):
    reason: str = "patched"  # patched | accepted | wont_fix
    accepted_rationale: str | None = None


@router.get("/vulnerabilities", response_class=HTMLResponse)
def vulnerabilities_page(request: Request):
    state = get_state()
    queue = vulnerabilities_store.list_triage_queue(limit=100)
    counts = vulnerabilities_store.counts_by_severity()
    avg_age = vulnerabilities_store.average_age_days()
    return templates.TemplateResponse(
        request=request,
        name="vulnerabilities.html",
        context={
            "state": state,
            "queue": queue,
            "counts": counts,
            "avg_age": avg_age,
        },
    )


@router.post("/api/vulnerabilities/{vuln_id}/triage")
def triage(vuln_id: str, body: TriageBody) -> JSONResponse:
    vulnerabilities_store.triage(vuln_id, severity=body.severity, notes=body.notes)
    return JSONResponse({"ok": True})


@router.post("/api/vulnerabilities/{vuln_id}/assign")
def assign(vuln_id: str, body: AssignBody) -> JSONResponse:
    vulnerabilities_store.assign(vuln_id, assigned_to=body.assigned_to,
                                 due_at=body.due_at)
    return JSONResponse({"ok": True})


@router.post("/api/vulnerabilities/{vuln_id}/close")
def close_vuln(vuln_id: str, body: CloseBody) -> JSONResponse:
    vulnerabilities_store.close(vuln_id, reason=body.reason,
                                accepted_rationale=body.accepted_rationale)
    return JSONResponse({"ok": True})


@router.post("/api/vulnerabilities/{vuln_id}/promote")
def promote(vuln_id: str) -> JSONResponse:
    risk_id = vulnerabilities_store.promote_to_risk(vuln_id)
    if not risk_id:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"ok": True, "risk_id": risk_id})
