"""Security philosophy doc endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.claude import philosophy as philosophy_helper
from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.redact.engine import apply_redactions

router = APIRouter()
api = APIRouter(prefix="/api/philosophy")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@api.get("")
async def latest() -> dict:
    doc = philosophy_helper.latest()
    return doc or {"empty": True}


@api.post("/seed")
@limiter.limit("3/hour")
async def seed(request: Request) -> dict:
    rid = philosophy_helper.seed()
    return {"report_id": rid} if rid else {"error": "failed"}


@api.post("/evolve")
@limiter.limit("3/hour")
async def evolve(request: Request) -> dict:
    rid = philosophy_helper.evolve()
    return {"report_id": rid} if rid else {"error": "failed"}


class RefineBody(BaseModel):
    freewrite: str = Field(min_length=1, max_length=20_000)


@api.post("/refine")
@limiter.limit("10/hour")
async def refine_endpoint(request: Request, body: RefineBody) -> dict:
    doc = philosophy_helper.latest()
    if not doc or doc.get("empty"):
        raise HTTPException(400, "No philosophy doc exists yet; seed one first.")
    redacted = apply_redactions(body.freewrite)
    loop = asyncio.get_event_loop()
    rid = await loop.run_in_executor(
        None,
        philosophy_helper.refine,
        redacted.redacted_text,
        doc["content_md"],
    )
    return {"report_id": rid} if rid else {"error": "failed"}


@router.get("/philosophy", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="philosophy.html",
        context={"doc": philosophy_helper.latest()},
    )


router.include_router(api)
