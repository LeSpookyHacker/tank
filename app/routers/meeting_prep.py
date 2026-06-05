"""Meeting-prep endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.claude.meeting_prep import prepare
from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.role import get_state

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class PrepRequest(BaseModel):
    who: str = Field(max_length=500)
    when: str | None = Field(default=None, max_length=100)
    extras: str | None = Field(default=None, max_length=5_000)


@router.get("/meeting-prep", response_class=HTMLResponse)
async def meeting_prep_page(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request=request, name="meeting_prep.html",
        context={"state": state},
    )


@router.post("/api/meeting-prep")
@limiter.limit("20/hour")
async def meeting_prep(request: Request, req: PrepRequest) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: prepare(who=req.who, when=req.when, extras=req.extras),
    )
