"""FastAPI entry point.

Owns:
- App-wide middleware (security headers, optional API-key gate).
- Lifespan: DB init + scheduler start/stop.
- `/healthz` liveness probe for systemd.
- Router wiring (one `include_router` per feature area).

If you're adding a new feature, you typically only need to:
1. Create the router under `app/routers/<feature>.py`.
2. Append a single `app.include_router(<feature>.router)` line below.

If you're adding a feature that needs to run on a schedule, wire it in
`app/claude/scheduler.py` instead — not here.
"""
from __future__ import annotations

import logging
import os
import secrets as _secrets
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.claude import scheduler
from app.config import STATIC_DIR
from app.db import get_conn
from app.rate_limiter import limiter
from app.routers import (
    attack_surface, auth, chat, compliance, decisions, design_reviews, detections,
    discovery, dfd, entities, followups, glossary, iam, ingest, integrations,
    intake, ir_runbooks, journal, kanban, lessons, me, meeting_prep, notes, nudges,
    onboarding, ownership, pages, philosophy, plan, policies, postmortems, projects,
    reports, risks, security_program, settings, stack_audit, subscriptions,
    tabletops, teams, threat_models, vulnerabilities, dashboard,
)

log = logging.getLogger("tank.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite schema (and load sqlite-vec if available) on
    # startup so the first request doesn't pay the cost.
    get_conn()
    # Warm the sentence-transformers model now so HuggingFace Hub's
    # "unauthenticated requests" warning fires at startup (predictable)
    # instead of mid-ingest (confusing). No-op if already cached.
    try:
        from app.ingest.embedder import _load_model
        _load_model()
    except Exception as _e:
        log.warning("embedder warm-up failed (non-fatal): %s", _e)
    # Start the partner-mode scheduler (digest, reflection, journal
    # prompt, anniversary). Single asyncio.Task; cleanly cancelled on
    # shutdown.
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title="Tank", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        nonce = _secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' cdn.jsdelivr.net unpkg.com; "
            # SEC-002: inline style= attributes migrated to CSS classes or nonce-protected <style>
            # blocks. 'unsafe-inline' is intentionally included in style-src because Mermaid
            # (v11+) injects a <style> block and inline style="" attributes into its dynamically-
            # rendered SVG output. Mermaid's SVG is generated entirely at runtime by the JS
            # library — we cannot attach a CSP nonce to it. Without 'unsafe-inline', Chrome blocks
            # the Mermaid <style> block and all SVG style="" attributes, causing all node shapes
            # and edges to render invisibly (black fill = default SVG, on dark background).
            # Tank is a local-only app so the XSS risk surface for style-src is minimal.
            # Note: 'unsafe-inline' in style-src does NOT allow inline JS — script-src remains strict.
            f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net; "
            "font-src fonts.gstatic.com cdn.jsdelivr.net; "
            "img-src 'self' data: blob: cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "worker-src 'self' blob:; "
            "frame-ancestors 'none';"
        )
        return response


app.add_middleware(_SecurityHeadersMiddleware)


# ── API-key gate ──────────────────────────────────────────────────────────────
# TANK_API_KEY is required when the server is not bound to localhost.
# Set it in .env: TANK_API_KEY=$(openssl rand -hex 32)
# Clients authenticate via:
#   1. HttpOnly session cookie (preferred — set by POST /api/auth/session)
#   2. X-Tank-Key header (legacy / programmatic use)
# Exempted: /healthz, /static/*, /api/auth/* (bootstrap + probes).
_TANK_API_KEY = os.environ.get("TANK_API_KEY", "").strip()
_BIND_HOST = os.environ.get("TANK_BIND_HOST", "").strip() or "127.0.0.1"

if not _TANK_API_KEY and _BIND_HOST not in ("127.0.0.1", "::1", "localhost"):
    print(
        "FATAL: TANK_API_KEY must be set when TANK_BIND_HOST is not 127.0.0.1.\n"
        "  Generate one with: openssl rand -hex 32\n"
        "  Then add TANK_API_KEY=<value> to your .env file.",
        file=sys.stderr,
    )
    sys.exit(1)

_AUTH_EXEMPT_PREFIXES = ("/healthz", "/static/", "/api/auth/")


class _APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not _TANK_API_KEY:
            return await call_next(request)
        path = request.url.path
        if any(path == p or path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        # Accept either a valid session cookie or the raw key header.
        from app.routers.auth import _COOKIE_NAME, is_valid_session
        session_token = request.cookies.get(_COOKIE_NAME, "")
        provided_key = request.headers.get("X-Tank-Key", "")

        key_ok = bool(provided_key) and _secrets.compare_digest(
            provided_key, _TANK_API_KEY
        )
        session_ok = bool(session_token) and is_valid_session(session_token)

        if not (key_ok or session_ok):
            try:
                from app.storage.audit_log_store import record as _audit
                _audit(
                    action="failed_auth",
                    detail={"remote": str(
                        request.client.host if request.client else "unknown"
                    )},
                )
            except Exception:
                pass
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


app.add_middleware(_APIKeyMiddleware)


@app.get("/healthz")
def healthz() -> dict:
    """Liveness + readiness probe for systemd / external supervisors.

    Returns 200 with a JSON status doc. The shape is shallow on purpose
    so supervisors can just inspect the HTTP status. Useful fields:

    - `scheduler`: "running" | "stopped"
    - `db`: "ok" | error message
    - `tenure_day`: int (0 if not onboarded yet)
    """
    db_status = "ok"
    try:
        get_conn().execute("SELECT 1").fetchone()
    except Exception as exc:
        db_status = f"error: {exc.__class__.__name__}"
    sched_status = "running" if scheduler.is_running() else "stopped"
    return {
        "ok": db_status == "ok",
        "scheduler": sched_status,
        "db": db_status,
    }

# Navigation hub (replaces pages.router for /, /dashboard, /teams/*, /search)
app.include_router(dashboard.router)
# Legacy pages (onboarding, /api/usage/cost; /ingest now lives in project workspace)
app.include_router(pages.router)
app.include_router(onboarding.router)
# First-hire intake interview
app.include_router(intake.router)
# Org discovery wizard
app.include_router(discovery.router)
# Security stack audit
app.include_router(stack_audit.router)
# Security policies
app.include_router(policies.router)
# Vulnerability triage workflow
app.include_router(vulnerabilities.router)
# 90-Day Plan
app.include_router(plan.router)

# Data layer
app.include_router(ingest.router)

# Chat
app.include_router(chat.router)

# Reports
app.include_router(reports.router)

# Partner mode
app.include_router(nudges.router)
app.include_router(meeting_prep.router)
app.include_router(notes.router)
app.include_router(journal.router)
app.include_router(journal.page)
app.include_router(followups.router)
app.include_router(kanban.router)
app.include_router(kanban.page)
app.include_router(subscriptions.router)
app.include_router(subscriptions.page)

# UI polish
app.include_router(entities.router)
app.include_router(settings.router)

# Opt-in connectors (Phase 11)
app.include_router(integrations.router)

# Phase 12: living threat models + decisions log
app.include_router(threat_models.router)
app.include_router(decisions.router)

# Phase 13: security workstreams
app.include_router(design_reviews.router)
app.include_router(postmortems.router)
app.include_router(tabletops.router)

# Phase 14: coverage + visibility
app.include_router(detections.router)
app.include_router(compliance.router)
app.include_router(attack_surface.router)
app.include_router(iam.router)

# Phase 15: continuous learning + memory
app.include_router(lessons.router)
app.include_router(glossary.router)
app.include_router(me.router)
app.include_router(ownership.router)
app.include_router(philosophy.router)

# Phase 16 + redesign: project compartmentalization + team hierarchy
app.include_router(projects.router)
app.include_router(teams.router)

# DFD threat modeling
app.include_router(dfd.router)

# Security program health + risk register
app.include_router(risks.router)
app.include_router(security_program.router)

# Gap 5: IR runbooks
app.include_router(ir_runbooks.router)

# Auth session management (SEC-001)
app.include_router(auth.router)
