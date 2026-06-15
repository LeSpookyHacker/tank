"""Decisions log endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import decisions as decisions_helper
from app.config import TEMPLATES_DIR
from app.redact.engine import apply_redactions
from app.storage import decisions_store

router = APIRouter()
api = APIRouter(prefix="/api/decisions")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateDecision(BaseModel):
    title: str
    body_md: str
    kind: str = "design_choice"
    scope_entity_ids: list[str] = []
    rationale: str | None = None
    expires_at: float | None = None
    owner_entity_id: str | None = None


class StatusUpdate(BaseModel):
    status: str


@api.get("")
async def list_filtered(kind: str | None = None,
                        status: str | None = "open") -> dict:
    return {"decisions": decisions_store.list_filtered(
        kind=kind, status=status,
    )}


@api.get("/expiring")
async def expiring(
    within_days: int = Query(default=7, ge=1, le=365),
) -> dict:
    return {"decisions": decisions_store.expiring_soon(within_days=within_days)}


@api.get("/recent")
async def recent(days: int = Query(default=30, ge=1, le=730)) -> dict:
    return {"decisions": decisions_store.recent(days=days)}


@api.get("/{decision_id}")
async def get_one(decision_id: str) -> dict:
    d = decisions_store.get(decision_id)
    if not d:
        raise HTTPException(404, "not found")
    return d


@api.post("")
async def create(body: CreateDecision) -> dict:
    title_red = apply_redactions(body.title).redacted_text
    body_red  = apply_redactions(body.body_md).redacted_text
    did = decisions_store.create(
        title=title_red, body_md=body.body_md,
        body_md_redacted=body_red, kind=body.kind,
        scope_entity_ids=body.scope_entity_ids,
        rationale=body.rationale, expires_at=body.expires_at,
        owner_entity_id=body.owner_entity_id,
        source="manual",
    )
    return {"id": did}


@api.put("/{decision_id}/status")
async def update_status(decision_id: str, body: StatusUpdate) -> dict:
    if not decisions_store.get(decision_id):
        raise HTTPException(404, "not found")
    decisions_store.set_status(decision_id, body.status)
    return {"ok": True}


@api.post("/{decision_id}/reaffirm")
async def reaffirm(decision_id: str, extend_days: int = 90) -> dict:
    if not decisions_store.get(decision_id):
        raise HTTPException(404, "not found")
    decisions_store.reaffirm(decision_id, extend_days=extend_days)
    return {"ok": True}


@api.post("/extract-from/{doc_id}")
async def extract_from_doc(doc_id: str) -> dict:
    """Run Sonnet to propose decisions from a document. No commit."""
    payload = decisions_helper.extract_from_doc(doc_id)
    if payload is None:
        return {"decisions": []}
    return {"decisions": [d.model_dump() for d in payload.decisions]}


class CommitExtraction(BaseModel):
    doc_id: str
    accept_indices: list[int] | None = None
    decisions: list[dict]  # pre-extracted payload, sent back from the diff UI


@api.post("/commit-extraction")
async def commit_extraction(body: CommitExtraction) -> dict:
    from app.schemas import DecisionExtraction, ExtractedDecision
    payload = DecisionExtraction(decisions=[
        ExtractedDecision(**d) for d in body.decisions
    ])
    ids = decisions_helper.commit_extraction(
        body.doc_id, payload, accept_indices=body.accept_indices,
    )
    return {"committed_ids": ids}


@router.get("/decisions", response_class=HTMLResponse)
def page_list(request: Request, kind: str | None = None,
              status: str = "open"):
    rows = decisions_store.list_filtered(kind=kind, status=status)
    return templates.TemplateResponse(
        request=request,
        name="decisions.html",
        context={"decisions": rows, "kind": kind, "status": status,
                 "expiring": decisions_store.expiring_soon(within_days=7)},
    )


router.include_router(api)
