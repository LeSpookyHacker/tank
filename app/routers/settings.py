"""Settings endpoints + wipe-all."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.db import db_path
from app.rate_limiter import limiter
from app.redact import config as redact_config
from app.redact.store import category_summary
from app.role import RoleMode, get_state, update_state

# The exact phrase a user has to type to wipe everything. Case-
# sensitive on purpose so a stale tab's autofill can't trip it.
WIPE_PHRASE = "delete tank"

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CategoryToggle(BaseModel):
    category: str
    enabled: bool


class CustomRule(BaseModel):
    category: str
    pattern: str
    placeholder_fmt: str | None = None
    description: str | None = None


class RolePut(BaseModel):
    role_mode: str


class CadencePut(BaseModel):
    digest_time: str | None = None
    reflection_day: str | None = None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    state = get_state()
    rules = redact_config.get_effective_rules()
    redaction_counts = category_summary()
    return templates.TemplateResponse(
        request=request, name="settings.html",
        context={"state": state, "rules": rules,
                 "redaction_counts": redaction_counts,
                 "db_path": str(db_path())},
    )


# ---------------- redaction ----------------

@router.post("/api/redaction/toggle")
async def toggle_category(body: CategoryToggle) -> dict:
    redact_config.set_category_enabled(body.category, body.enabled)
    return {"ok": True}


@router.post("/api/redaction/custom")
async def add_custom(body: CustomRule) -> dict:
    try:
        rid = redact_config.add_custom_rule(
            body.category, body.pattern,
            placeholder_fmt=body.placeholder_fmt,
            description=body.description,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"id": rid}


@router.delete("/api/redaction/custom/{rule_id}")
async def remove_custom(rule_id: int) -> dict:
    redact_config.remove_custom_rule(rule_id)
    return {"ok": True}


# ---------------- role + cadence ----------------

@router.put("/api/role/mode")
async def set_role(body: RolePut) -> dict:
    try:
        rm = RoleMode(body.role_mode)
    except ValueError:
        raise HTTPException(400, "invalid role_mode")
    update_state(role_mode=rm)
    return {"ok": True}


@router.put("/api/cadence")
async def set_cadence(body: CadencePut) -> dict:
    update_state(digest_time=body.digest_time,
                 reflection_day=body.reflection_day)
    return {"ok": True}


# ---------------- nuke ----------------

@router.post("/api/wipe")
@limiter.limit("3/hour")
async def wipe_all(request: Request, confirm_phrase: str = Form(...),
                   wipe_backups: bool = Form(default=False)):
    """Delete the SQLite DB. The next request reinitializes.

    Requires:
    1. The literal string `WIPE_PHRASE` ("delete tank") in `confirm_phrase`.
    2. The custom header `X-Confirm: delete-tank` — browsers cannot set custom
       headers in plain form submissions, so this blocks CSRF attacks.

    Pass `wipe_backups=true` to also delete weekly backup copies in
    `~/.tank/backups/`. These backups contain the full redaction_map with
    original plaintext values; wipe them if you need to remove all stored PII.
    """
    if request.headers.get("X-Confirm") != "delete-tank":
        raise HTTPException(403, "missing or invalid X-Confirm header")
    if confirm_phrase != WIPE_PHRASE:
        raise HTTPException(
            400,
            f"refused: must type exactly {WIPE_PHRASE!r} to confirm wipe.",
        )

    from app.storage.audit_log_store import log_action
    log_action("wipe", remote_addr=request.client.host if request.client else None)

    p = db_path()
    if p.exists():
        p.unlink()
    for sfx in ("-wal", "-shm"):
        s = Path(str(p) + sfx)
        if s.exists():
            s.unlink()

    if wipe_backups:
        backup_dir = p.parent / "backups"
        if backup_dir.is_dir():
            for f in backup_dir.glob("*.sqlite"):
                f.unlink(missing_ok=True)

    # Reset cached connection.
    import app.db as db_mod
    db_mod._CONN = None
    return RedirectResponse(url="/onboarding", status_code=303)
