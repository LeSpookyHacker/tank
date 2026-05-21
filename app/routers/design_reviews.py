"""Design review endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude import design_review as design_review_helper
from app.config import TEMPLATES_DIR
from app.storage import decisions_store, design_reviews_store

router = APIRouter()
api = APIRouter(prefix="/api/design-reviews")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateReview(BaseModel):
    title: str
    freewrite: str
    requester: str | None = None


class ChecklistUpdate(BaseModel):
    checklist: list[dict]


class StatusUpdate(BaseModel):
    status: str


class DecisionFromReview(BaseModel):
    title: str
    body_md: str
    kind: str = "design_choice"
    rationale: str | None = None
    expires_at: float | None = None


@api.get("")
async def list_reviews(status: str | None = None) -> dict:
    if status:
        return {"design_reviews": design_reviews_store.list_by_status(status)}
    return {"design_reviews": design_reviews_store.list_all()}


@api.post("")
async def create_review(body: CreateReview) -> dict:
    dr_id = design_review_helper.seed_intake(
        title=body.title, freewrite=body.freewrite,
        requester=body.requester,
    )
    return {"id": dr_id}


@api.get("/{dr_id}")
async def get_review(dr_id: str) -> dict:
    dr = design_reviews_store.get(dr_id)
    if not dr:
        raise HTTPException(404, "not found")
    return dr


@api.put("/{dr_id}/checklist")
async def update_checklist(dr_id: str, body: ChecklistUpdate) -> dict:
    if not design_reviews_store.get(dr_id):
        raise HTTPException(404, "not found")
    design_reviews_store.update_checklist(dr_id, body.checklist)
    return {"ok": True}


@api.put("/{dr_id}/status")
async def update_status(dr_id: str, body: StatusUpdate) -> dict:
    dr = design_reviews_store.get(dr_id)
    if not dr:
        raise HTTPException(404, "not found")
    design_reviews_store.set_status(dr_id, body.status)
    # Phase-15 hook: on rejection, extract any generalizable lessons.
    if body.status == "rejected":
        try:
            from app.claude import lesson_extractor
            lesson_extractor.extract_from_design_review(
                dr_id, dr.get("body_md_redacted") or dr.get("body_md") or "",
            )
        except Exception:
            pass
    return {"ok": True}


@api.post("/{dr_id}/decisions")
async def add_decision(dr_id: str, body: DecisionFromReview) -> dict:
    """Spawn a decision row sourced from this review."""
    dr = design_reviews_store.get(dr_id)
    if not dr:
        raise HTTPException(404, "not found")
    did = decisions_store.create(
        title=body.title, body_md=body.body_md,
        body_md_redacted=body.body_md, kind=body.kind,
        scope_entity_ids=dr.get("scope_entity_ids") or [],
        rationale=body.rationale, expires_at=body.expires_at,
        source="design_review", source_doc_id=None,
    )
    design_reviews_store.add_decision(dr_id, did)
    return {"decision_id": did}


@router.get("/design-reviews", response_class=HTMLResponse)
def page_list(request: Request, status: str = "intake"):
    rows = design_reviews_store.list_by_status(status) if status else \
           design_reviews_store.list_all()
    return templates.TemplateResponse(
        request=request,
        name="design_reviews.html",
        context={"reviews": rows, "status": status},
    )


@router.get("/design-reviews/new", response_class=HTMLResponse)
def page_new(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="design_review_new.html",
        context={},
    )


@router.get("/design-reviews/{dr_id}", response_class=HTMLResponse)
def page_detail(request: Request, dr_id: str):
    dr = design_reviews_store.get(dr_id)
    if not dr:
        raise HTTPException(404, "not found")
    return templates.TemplateResponse(
        request=request,
        name="design_review_detail.html",
        context={"review": dr},
    )


router.include_router(api)
