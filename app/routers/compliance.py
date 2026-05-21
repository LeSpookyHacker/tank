"""Compliance / evidence endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.claude import compliance as compliance_helper
from app.config import TEMPLATES_DIR
from app.kb import compliance as compliance_kb
from app.storage import entities_store

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


router.include_router(api)
