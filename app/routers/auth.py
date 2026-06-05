"""Session authentication for the TANK_API_KEY gate.

When TANK_API_KEY is set, users POST their key here once and receive an
HttpOnly session cookie valid for 12 hours.  Subsequent requests carry the
cookie automatically — the key is never stored in browser storage.

Endpoints are exempt from the API-key middleware (added to
_AUTH_EXEMPT_PREFIXES in main.py) so the login round-trip can complete.
"""
from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.rate_limiter import limiter

router = APIRouter(prefix="/api/auth")

_COOKIE_NAME = "tank_session"
_SESSION_TTL = 12 * 3600  # 12 hours

# In-memory session store: token → expiry epoch.
# Lost on server restart (users re-login, which is acceptable for a
# local-first tool).
_SESSIONS: dict[str, float] = {}


def is_valid_session(token: str) -> bool:
    """Return True if the token exists and has not expired."""
    expiry = _SESSIONS.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        _SESSIONS.pop(token, None)
        return False
    return True


class _AuthIn(BaseModel):
    key: str = Field(max_length=256)


@router.post("/session")
@limiter.limit("5/minute")
def create_session(request: Request, body: _AuthIn) -> JSONResponse:
    """Validate TANK_API_KEY and issue an HttpOnly session cookie."""
    import secrets as _sec
    from app.main import _TANK_API_KEY  # imported lazily to avoid circular

    if not _TANK_API_KEY:
        # No key configured — auth is not required; acknowledge gracefully.
        return JSONResponse({"ok": True, "msg": "auth not required"})

    if not _sec.compare_digest(body.key.strip(), _TANK_API_KEY):
        raise HTTPException(status_code=401, detail="invalid key")

    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = time.time() + _SESSION_TTL

    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=(request.url.scheme == "https"),
        max_age=_SESSION_TTL,
    )
    return resp


@router.delete("/session")
def delete_session(request: Request) -> JSONResponse:
    """Invalidate the current session and clear the cookie."""
    token = request.cookies.get(_COOKIE_NAME, "")
    _SESSIONS.pop(token, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_COOKIE_NAME, samesite="strict")
    return resp


@router.get("/status")
def auth_status(request: Request) -> dict:
    """Return whether the current request is authenticated and if auth is required."""
    from app.main import _TANK_API_KEY
    required = bool(_TANK_API_KEY)
    if not required:
        return {"required": False, "authenticated": True}
    token = request.cookies.get(_COOKIE_NAME, "")
    return {"required": True, "authenticated": is_valid_session(token)}
