"""Security philosophy doc endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.claude import philosophy as philosophy_helper
from app.config import TEMPLATES_DIR

router = APIRouter()
api = APIRouter(prefix="/api/philosophy")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@api.get("")
async def latest() -> dict:
    doc = philosophy_helper.latest()
    return doc or {"empty": True}


@api.post("/seed")
async def seed() -> dict:
    rid = philosophy_helper.seed()
    return {"report_id": rid} if rid else {"error": "failed"}


@api.post("/evolve")
async def evolve() -> dict:
    rid = philosophy_helper.evolve()
    return {"report_id": rid} if rid else {"error": "failed"}


@router.get("/philosophy", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="philosophy.html",
        context={"doc": philosophy_helper.latest()},
    )


router.include_router(api)
