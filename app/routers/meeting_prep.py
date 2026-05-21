"""Meeting-prep endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.claude.meeting_prep import prepare
from app.config import TEMPLATES_DIR
from app.role import get_state

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class PrepRequest(BaseModel):
    who: str
    when: str | None = None
    extras: str | None = None


@router.get("/meeting-prep", response_class=HTMLResponse)
async def meeting_prep_page(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request=request, name="meeting_prep.html",
        context={"state": state},
    )


@router.post("/api/meeting-prep")
async def meeting_prep(req: PrepRequest) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: prepare(who=req.who, when=req.when, extras=req.extras),
    )
