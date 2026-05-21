"""Onboarding endpoints — 5-step conversational intake.

Phase-1 shipped a skip-only stub. This is the full flow:

1. Role frame (IC / Manager / Both).
2. Scope sketch (paste offer letter or freewrite → extract chips).
3. Calendar dump (paste or .ics URL → seed people graph; optional).
4. Initial docs (drop-in or skip; background-ingested).
5. Cadence (digest time, reflection day).

At the end, we set `tenure_started_at` and kick off the Day-1 brief.
The brief is rendered as a Report (`kind='day1_brief'`).
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.role import RoleMode, UserScope, get_state, update_state

router = APIRouter(prefix="/api/onboarding")
log = logging.getLogger("tank.onboarding")


class SetRoleMode(BaseModel):
    role_mode: str    # 'ic'|'manager'|'both'


class SetScope(BaseModel):
    freewrite: str
    domain: str | None = None
    org: str | None = None
    manager: str | None = None
    priorities: list[str] = []


class SetCadence(BaseModel):
    digest_time: str = "08:00"
    reflection_day: str = "fri"


class SetInternalTLD(BaseModel):
    internal_tld: str | None = None


@router.post("/role")
async def set_role(body: SetRoleMode) -> dict:
    try:
        rm = RoleMode(body.role_mode)
    except ValueError:
        return {"error": "invalid role_mode"}
    update_state(role_mode=rm)
    return {"ok": True}


@router.post("/scope")
async def set_scope(body: SetScope) -> dict:
    scope = UserScope(
        freewrite=body.freewrite,
        domain=body.domain,
        org=body.org,
        manager=body.manager,
        priorities=body.priorities,
    )
    update_state(user_scope=scope)
    return {"ok": True}


@router.post("/internal-tld")
async def set_tld(body: SetInternalTLD) -> dict:
    update_state(internal_tld=body.internal_tld or "")
    return {"ok": True}


@router.post("/cadence")
async def set_cadence(body: SetCadence) -> dict:
    update_state(digest_time=body.digest_time,
                 reflection_day=body.reflection_day)
    return {"ok": True}


@router.post("/complete")
async def complete(background_tasks: BackgroundTasks) -> dict:
    """Mark onboarding complete, set tenure_started_at, kick off Day-1 brief."""
    update_state(onboarded=True, tenure_started_at=time.time())
    background_tasks.add_task(_generate_day1_brief)
    return {"ok": True, "redirect": "/"}


@router.post("/skip")
async def skip() -> RedirectResponse:
    """Legacy skip — leaves Day-1 brief ungenerated."""
    update_state(onboarded=True, tenure_started_at=time.time())
    return RedirectResponse(url="/", status_code=303)


def _generate_day1_brief() -> None:
    try:
        from app.claude.day1_brief import generate
        generate()
    except Exception:
        log.exception("Day-1 brief generation failed")
