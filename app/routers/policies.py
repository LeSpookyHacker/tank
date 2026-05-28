"""Security Policy Scaffolding — five living first-draft policies.

Routes:
  GET  /policies                     — list all 5 policy kinds with status
  GET  /policies/{kind}              — detail / editor view
  POST /api/policies/generate        — generate a policy from KB context
  PUT  /api/policies/{id}            — update content or status
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import policies_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.policies")


class GeneratePolicyBody(BaseModel):
    kind: str


class UpdatePolicyBody(BaseModel):
    content_md: str
    status: str | None = None


@router.get("/policies", response_class=HTMLResponse)
def policies_list(request: Request):
    state = get_state()
    policies = policies_store.list_all()
    return templates.TemplateResponse(
        request=request,
        name="policies.html",
        context={
            "state": state,
            "policies": policies,
            "policy_display_names": policies_store.POLICY_DISPLAY_NAMES,
            "policy_kinds": policies_store.POLICY_KINDS,
        },
    )


@router.get("/policies/{kind}", response_class=HTMLResponse)
def policy_detail(kind: str, request: Request):
    if kind not in policies_store.POLICY_KINDS:
        return HTMLResponse("Unknown policy kind", status_code=404)
    state = get_state()
    policy = policies_store.get_latest(kind)
    return templates.TemplateResponse(
        request=request,
        name="policy_detail.html",
        context={
            "state": state,
            "policy": policy,
            "kind": kind,
            "display_name": policies_store.POLICY_DISPLAY_NAMES.get(kind, kind),
        },
    )


@router.post("/api/policies/generate")
async def generate_policy(
    body: GeneratePolicyBody,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    if body.kind not in policies_store.POLICY_KINDS:
        return JSONResponse({"error": "Unknown policy kind"}, status_code=422)
    background_tasks.add_task(_generate_bg, body.kind)
    return JSONResponse({"ok": True, "kind": body.kind,
                         "message": "Generation started. Check back in ~30 seconds."})


@router.put("/api/policies/{policy_id}")
def update_policy(policy_id: str, body: UpdatePolicyBody) -> JSONResponse:
    policy = policies_store.get_by_id(policy_id)
    if not policy:
        return JSONResponse({"error": "Not found"}, status_code=404)
    from app.redact.engine import apply_redactions
    redacted = apply_redactions(body.content_md).redacted_text
    policies_store.update(
        policy_id,
        content_md=body.content_md,
        content_md_redacted=redacted,
        status=body.status,
    )
    return JSONResponse({"ok": True})


def _generate_bg(kind: str) -> None:
    try:
        from app.claude.policy_generator import generate
        generate(kind)
    except Exception:
        log.exception("policy generation failed for kind=%r", kind)
