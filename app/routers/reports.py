"""Reports endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude.reports import REPORT_REGISTRY
from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import reports_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.routers.reports")


class GenerateRequest(BaseModel):
    scope: dict | None = None


# ---------------- HTML ----------------

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    state = get_state()
    by_kind: dict[str, list[dict]] = {}
    for kind in REPORT_REGISTRY:
        by_kind[kind] = reports_store.list_by_kind(kind=kind, limit=5)
    return templates.TemplateResponse(
        request=request, name="reports.html",
        context={"state": state, "by_kind": by_kind,
                 "kinds": list(REPORT_REGISTRY.keys())},
    )


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(request: Request, report_id: str):
    rpt = reports_store.get(report_id)
    if not rpt:
        raise HTTPException(404, "no such report")
    state = get_state()
    return templates.TemplateResponse(
        request=request, name="report_detail.html",
        context={"state": state, "report": rpt},
    )


# ---------------- API ----------------

@router.post("/api/reports/{kind}")
async def generate_report(kind: str, body: GenerateRequest) -> dict:
    gen = REPORT_REGISTRY.get(kind)
    if gen is None:
        raise HTTPException(404, f"unknown report kind: {kind}")

    scope = body.scope or {}
    try:
        if kind == "threat_landscape":
            service_id = scope.get("service_id")
            if not service_id:
                raise HTTPException(400, "scope.service_id required")
            report_id = await asyncio.get_event_loop().run_in_executor(
                None, gen, service_id,
            )
        elif kind == "questions_for_team":
            who = scope.get("team_or_person")
            if not who:
                raise HTTPException(400, "scope.team_or_person required")
            report_id = await asyncio.get_event_loop().run_in_executor(
                None, gen, who,
            )
        else:
            report_id = await asyncio.get_event_loop().run_in_executor(
                None, gen,
            )
    except Exception as exc:
        log.exception("report %s failed", kind)
        raise HTTPException(500, str(exc))

    return {"report_id": report_id}


@router.get("/api/reports")
async def list_reports(kind: str | None = None) -> dict:
    return {"reports": reports_store.list_by_kind(kind=kind)}


@router.get("/api/reports/{report_id}")
async def get_report(report_id: str) -> dict:
    rpt = reports_store.get(report_id)
    if not rpt:
        raise HTTPException(404, "no such report")
    return rpt


@router.get("/api/reports/{report_id}/export", response_class=PlainTextResponse)
async def export_report(report_id: str, format: str = "md") -> str:
    rpt = reports_store.get(report_id)
    if not rpt:
        raise HTTPException(404, "no such report")
    if format != "md":
        raise HTTPException(400, "only md export supported in v1")
    return rpt["content_md"]
