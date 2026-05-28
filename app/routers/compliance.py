"""Compliance / evidence endpoints + compliance framework selection wizard."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import compliance as compliance_helper
from app.config import TEMPLATES_DIR
from app.kb import compliance as compliance_kb
from app.role import get_state
from app.storage import entities_store

log = logging.getLogger("tank.compliance")

router = APIRouter()
api = APIRouter(prefix="/api/compliance")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@api.get("/controls")
async def list_controls() -> dict:
    return {"controls": entities_store.list_entities(
        type_="Control", limit=500,
    )}


@api.post("/collect-evidence")
async def collect_evidence() -> dict:
    """Run evidence collection across all Control entities."""
    out = compliance_helper.collect_for_framework()
    return out.model_dump()


@api.get("/evidence/{control_id}")
async def evidence_for(control_id: str) -> dict:
    return compliance_kb.find_evidence(control_id)


@api.get("/gaps")
async def gaps() -> dict:
    return {"control_ids_with_no_evidence":
            compliance_kb.controls_with_no_evidence()}


@router.get("/compliance", response_class=HTMLResponse)
def page(request: Request):
    controls = entities_store.list_entities(type_="Control", limit=500)
    gaps = set(compliance_kb.controls_with_no_evidence())
    return templates.TemplateResponse(
        request=request,
        name="compliance.html",
        context={"controls": controls, "gaps": gaps},
    )


@router.get("/compliance/wizard", response_class=HTMLResponse)
def wizard_page(request: Request):
    from app.claude.compliance_wizard import QUESTIONS
    state = get_state()
    return templates.TemplateResponse(
        request=request,
        name="compliance_wizard.html",
        context={"state": state, "questions": QUESTIONS},
    )


class WizardCompleteBody(BaseModel):
    answers: dict


@api.post("/wizard/complete")
async def wizard_complete(body: WizardCompleteBody,
                          background_tasks: BackgroundTasks) -> JSONResponse:
    background_tasks.add_task(_run_wizard_bg, body.answers)
    return JSONResponse({"ok": True,
                         "message": "Recommendation generating. Check Reports in ~30s."})


def _run_wizard_bg(answers: dict) -> None:
    try:
        from app.claude.compliance_wizard import recommend
        from app.storage import decisions_store
        result = recommend(answers)
        recs = result.get("recommendation", [])
        if recs:
            top = recs[0]
            framework = top.get("framework", "compliance framework")
            decisions_store.create(
                title=f"Compliance framework selection: {framework}",
                body_md=f"**Recommendation:** {framework}\n\n**Rationale:** {top.get('rationale','')}\n\n**Effort:** {top.get('effort_estimate','')}",
                body_md_redacted=f"Compliance framework: {framework}",
                kind="design_choice",
                source="manual",
                rationale=top.get("rationale", ""),
            )
    except Exception:
        log.exception("compliance wizard background task failed")


router.include_router(api)
