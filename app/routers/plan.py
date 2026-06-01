"""90-Day Plan — milestone-driven task list for the first-hire journey.

Routes:
  GET  /plan                   — plan view
  POST /api/plan/generate      — generate from KB + intake context
  PUT  /api/plan/task/{idx}    — check/uncheck a task
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.rate_limiter import limiter
from app.role import get_state, tenure_day as get_tenure_day
from app.storage import plan_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.plan")


class UpdateTaskBody(BaseModel):
    done: bool


@router.get("/plan", response_class=HTMLResponse)
def plan_page(request: Request):
    state = get_state()
    plan = plan_store.get_latest()
    tday = get_tenure_day()
    current_week = min(max((tday // 7) + 1, 1), 13)
    return templates.TemplateResponse(
        request=request,
        name="plan.html",
        context={
            "state": state,
            "plan": plan,
            "current_week": current_week,
            "tday": tday,
        },
    )


@router.post("/api/plan/generate")
@limiter.limit("5/hour")
async def generate_plan(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    background_tasks.add_task(_generate_bg)
    return JSONResponse({"ok": True,
                         "message": "Plan generation started. Refresh in ~30 seconds."})


@router.put("/api/plan/task/{task_index}")
def update_task(task_index: int, body: UpdateTaskBody) -> JSONResponse:
    plan = plan_store.get_latest()
    if not plan:
        return JSONResponse({"error": "No plan found"}, status_code=404)
    plan_store.update_task(plan["id"], task_index, body.done)
    return JSONResponse({"ok": True})


def _generate_bg() -> None:
    try:
        from app.claude.plan_generator import generate
        generate()
    except Exception:
        log.exception("90-day plan generation failed")
