"""Onboarding endpoints — minimal pre-intake gate.

Collects only what must be known before data collection starts:
  1. Role frame (IC / Manager / Both).
  2. Internal TLD (for redaction rules).

On complete, marks onboarded=True and redirects to /intake, where the
20-question structured interview seeds the entity graph and generates
the Day-1 brief. Cadence settings (digest time, reflection day) live
in Settings.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Literal

from app.role import RoleMode, UserScope, update_state

router = APIRouter(prefix="/api/onboarding")
log = logging.getLogger("tank.onboarding")


class SetRoleMode(BaseModel):
    role_mode: str    # 'ic'|'manager'|'both'


class SetScope(BaseModel):
    freewrite: str = Field(max_length=10_000)
    domain: str | None = Field(default=None, max_length=200)
    org: str | None = Field(default=None, max_length=200)
    manager: str | None = Field(default=None, max_length=200)
    priorities: list[str] = []


class SetCadence(BaseModel):
    digest_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    reflection_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] = "fri"


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
    from app.redact.engine import apply_redactions
    redacted_fw = apply_redactions(body.freewrite).redacted_text
    scope = UserScope(
        freewrite=redacted_fw,
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
async def complete() -> dict:
    """Mark onboarding complete, set tenure_started_at, redirect to intake."""
    update_state(onboarded=True, tenure_started_at=time.time())
    return {"ok": True, "redirect": "/intake"}


@router.post("/skip")
async def skip() -> RedirectResponse:
    """Skip onboarding entirely — lands on home; setup_banner will prompt intake."""
    update_state(onboarded=True, tenure_started_at=time.time())
    return RedirectResponse(url="/", status_code=303)
