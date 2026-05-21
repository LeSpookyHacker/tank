"""Server-rendered UI routes (home + onboarding gate)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.db import LOCK, get_conn
from app.role import current_lens, get_state, tenure_day
from app.storage import followups_store, nudges_store, usage_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    state = get_state()
    if not state.onboarded:
        return RedirectResponse(url="/onboarding", status_code=302)

    conn = get_conn()
    with LOCK:
        counts = {
            "documents": conn.execute(
                "SELECT COUNT(*) AS c FROM documents"
            ).fetchone()["c"],
            "entities": conn.execute(
                "SELECT COUNT(*) AS c FROM entities"
            ).fetchone()["c"],
            "redactions": conn.execute(
                "SELECT COUNT(*) AS c FROM redaction_map"
            ).fetchone()["c"],
            "conversations": conn.execute(
                "SELECT COUNT(*) AS c FROM conversations"
            ).fetchone()["c"],
        }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "state": state,
            "counts": counts,
            "lens": current_lens() if state.tenure_started_at else None,
            "tenure": tenure_day(),
            "nudges": nudges_store.list_open(limit=5),
            "followups": followups_store.list_by_status("open", limit=5),
            "hot_entities": usage_store.hot_entities(days=7, k=5),
        },
    )


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={"state": state},
    )
