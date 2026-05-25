"""Server-rendered UI routes (home + onboarding gate + ingest page)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.db import LOCK, get_conn
from app.role import current_lens, get_state, tenure_day
from app.storage import followups_store, nudges_store, usage_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _build_hints(counts: dict, lens: str | None, tday: int, conn) -> list[dict]:
    hints: list[dict] = []
    docs = counts.get("documents", 0)
    convs = counts.get("conversations", 0)

    if docs == 0:
        hints.append({
            "icon": "📂",
            "text": "You haven't ingested anything yet. Head to Ingest to upload your first doc — architecture diagrams, runbooks, or team wikis are a great start.",
            "link": "/ingest", "link_label": "Go to Ingest",
        })
    elif convs == 0:
        hints.append({
            "icon": "💬",
            "text": f"You have {docs} doc{'s' if docs != 1 else ''} in the KB. Try asking Tank something in Chat — e.g. 'What services do we run?' or 'Summarise the architecture.'",
            "link": "/chat", "link_label": "Open Chat",
        })

    if tday < 8 and docs > 0:
        hints.append({
            "icon": "🗓️",
            "text": "Day 1–7: Generate your Day-1 brief from the Reports page to get an instant overview of the landscape.",
            "link": "/reports", "link_label": "Reports",
        })

    if lens == "map":
        hints.append({
            "icon": "🗺️",
            "text": "Map mode: focus on who-owns-what. Browse Entities to find Service owners, then claim yours on the Me page.",
            "link": "/entities", "link_label": "Entities",
        })
    elif lens == "prioritize":
        hints.append({
            "icon": "🎯",
            "text": "Prioritize mode: generate a Threat Landscape or Cross-Service Gaps report to surface the highest-risk areas.",
            "link": "/reports", "link_label": "Reports",
        })
    elif lens == "execute":
        hints.append({
            "icon": "🚀",
            "text": "Execute mode: check your open Decisions for anything expiring soon, and review pending Design Reviews.",
            "link": "/design-reviews", "link_label": "Design Reviews",
        })

    with LOCK:
        expiring = conn.execute(
            "SELECT COUNT(*) AS c FROM decisions "
            "WHERE status='open' AND expires_at IS NOT NULL AND expires_at < ?",
            (time.time() + 7 * 86400,),
        ).fetchone()["c"]
    if expiring:
        hints.append({
            "icon": "⚠️",
            "text": f"{expiring} decision{'s' if expiring != 1 else ''} expiring in the next 7 days. Review and reaffirm or withdraw them.",
            "link": "/decisions", "link_label": "Decisions",
        })

    if not hints:
        hints.append({
            "icon": "✅",
            "text": "You're all caught up! Keep ingesting new docs as your understanding of the environment grows.",
            "link": None, "link_label": None,
        })

    return hints


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

    lens = current_lens() if state.tenure_started_at else None
    tday = tenure_day()
    hints = _build_hints(counts, lens, tday, conn)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "state": state,
            "counts": counts,
            "lens": lens,
            "tenure": tday,
            "nudges": nudges_store.list_open(limit=5),
            "followups": followups_store.list_by_status("open", limit=5),
            "hot_entities": usage_store.hot_entities(days=7, k=5),
            "hints": hints,
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


@router.get("/ingest", response_class=HTMLResponse)
def ingest_page(request: Request):
    state = get_state()
    conn = get_conn()
    with LOCK:
        docs = conn.execute(
            "SELECT id, title, kind, category, size_bytes, ingested_at "
            "FROM documents ORDER BY ingested_at DESC LIMIT 30"
        ).fetchall()
    return templates.TemplateResponse(
        request=request,
        name="ingest.html",
        context={"state": state, "docs": [dict(d) for d in docs]},
    )


@router.get("/api/usage/cost")
def usage_cost() -> JSONResponse:
    conn = get_conn()
    with LOCK:
        m = conn.execute(
            "SELECT COALESCE(SUM(tokens_in),0) AS ti, "
            "       COALESCE(SUM(tokens_out),0) AS to_, "
            "       COALESCE(SUM(cache_read_in),0) AS cr, "
            "       COALESCE(SUM(cache_create_in),0) AS cc "
            "FROM messages"
        ).fetchone()
        r = conn.execute(
            "SELECT COALESCE(SUM(tokens_in),0) AS ti, "
            "       COALESCE(SUM(tokens_out),0) AS to_, "
            "       COALESCE(SUM(cache_read_in),0) AS cr, "
            "       COALESCE(SUM(cache_create_in),0) AS cc "
            "FROM reports"
        ).fetchone()
        a = conn.execute(
            "SELECT COALESCE(SUM(tokens_in),0) AS ti, "
            "       COALESCE(SUM(tokens_out),0) AS to_, "
            "       COALESCE(SUM(cache_read_in),0) AS cr, "
            "       COALESCE(SUM(cache_create_in),0) AS cc "
            "FROM api_calls"
        ).fetchone()
    ti  = (m["ti"] or 0) + (r["ti"] or 0) + (a["ti"] or 0)
    to_ = (m["to_"] or 0) + (r["to_"] or 0) + (a["to_"] or 0)
    cr  = (m["cr"] or 0) + (r["cr"] or 0) + (a["cr"] or 0)
    cc  = (m["cc"] or 0) + (r["cc"] or 0) + (a["cc"] or 0)
    cost = (ti * 3.00 + to_ * 15.00 + cr * 0.30 + cc * 3.75) / 1_000_000
    return JSONResponse({
        "total_usd": round(cost, 4),
        "tokens_in": ti,
        "tokens_out": to_,
        "cache_read": cr,
        "cache_write": cc,
    })
