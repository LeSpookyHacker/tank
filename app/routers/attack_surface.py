"""Attack-surface ledger endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.claude import attack_surface as as_helper
from app.config import TEMPLATES_DIR

router = APIRouter()
api = APIRouter(prefix="/api/attack-surface")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@api.get("/latest")
async def latest() -> dict:
    snap = as_helper.latest()
    return snap or {"empty": True}


@api.get("/history")
async def history(limit: int = 12) -> dict:
    return {"history": as_helper.history(limit=limit)}


@api.post("/snapshot")
async def snapshot_now() -> dict:
    sid = as_helper.snapshot()
    return {"id": sid}


@router.get("/attack-surface", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="attack_surface.html",
        context={"latest": as_helper.latest(),
                 "history": as_helper.history(limit=8)},
    )


router.include_router(api)
