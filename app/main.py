from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.claude import scheduler
from app.config import STATIC_DIR
from app.db import get_conn
from app.routers import (
    attack_surface, chat, compliance, decisions, design_reviews, detections,
    dfd, entities, followups, glossary, iam, ingest, integrations, journal,
    lessons, me, meeting_prep, notes, nudges, onboarding, pages, philosophy,
    postmortems, projects, reports, settings, subscriptions, tabletops, threat_models,
)

log = logging.getLogger("tank.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite schema (and load sqlite-vec if available) on
    # startup so the first request doesn't pay the cost.
    get_conn()
    # Start the partner-mode scheduler (digest, reflection, journal
    # prompt, anniversary). Single asyncio.Task; cleanly cancelled on
    # shutdown.
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title="Tank", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    try:
        from app.role import tenure_day
        tday = tenure_day()
    except Exception:
        tday = 0
    return {
        "ok": db_status == "ok",
        "scheduler": sched_status,
        "db": db_status,
        "tenure_day": tday,
    }

# Pages + core
app.include_router(pages.router)
app.include_router(onboarding.router)

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
app.include_router(followups.router)
app.include_router(subscriptions.router)

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
app.include_router(philosophy.router)

# Phase 16: project compartmentalization
app.include_router(projects.router)

# DFD threat modeling
app.include_router(dfd.router)
