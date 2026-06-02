# pages.py — Server-rendered UI routes (home + onboarding gate + ingest page).
# Phase 5 (tankinstuction): home route validates/heals the active project context.
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.db import LOCK, get_conn
from app.role import current_lens, get_state, tenure_day
from app.storage import followups_store, nudges_store, usage_store
from app.storage.projects_store import get_active_project_id, get_project, set_active_project_id

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

    # Phase 5: validate the stored active project and self-heal if stale.
    active_id = get_active_project_id()
    active_project = get_project(active_id)
    if active_project is None:
        set_active_project_id("default")
        active_project = get_project("default")

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
        # Recent decisions for the home dashboard strip (last 3)
        recent_decisions = [
            dict(r) for r in conn.execute(
                "SELECT id, title, kind, created_at FROM decisions "
                "ORDER BY created_at DESC LIMIT 3"
            ).fetchall()
        ]

    lens = current_lens() if state.tenure_started_at else None
    tday = tenure_day()
    hints = _build_hints(counts, lens, tday, conn)

    # Setup banners for incomplete first-hire tasks
    setup_banners = []
    if not state.intake_completed:
        setup_banners.append({
            "id": "intake_incomplete",
            "text": "Complete your intake interview to unlock your Day-1 Brief and seed your knowledge graph.",
            "link": "/intake",
            "link_label": "Start intake interview →",
        })

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
            "active_project": active_project,
            "recent_decisions": recent_decisions,
            "setup_banners": setup_banners,
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


def _compute_cost(ti: int, to_: int, cr: int, cc: int) -> float:
    return (ti * 3.00 + to_ * 15.00 + cr * 0.30 + cc * 3.75) / 1_000_000


def _row_usd(row) -> dict:
    ti  = row["ti"] or 0
    to_ = row["to_"] or 0
    cr  = row["cr"] or 0
    cc  = row["cc"] or 0
    return {
        "tokens_in": ti,
        "tokens_out": to_,
        "cache_read": cr,
        "cache_write": cc,
        "usd": round(_compute_cost(ti, to_, cr, cc), 4),
    }


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
    cost = _compute_cost(ti, to_, cr, cc)
    return JSONResponse({
        "total_usd": round(cost, 4),
        "tokens_in": ti,
        "tokens_out": to_,
        "cache_read": cr,
        "cache_write": cc,
    })


@router.get("/api/usage/breakdown")
def usage_breakdown() -> JSONResponse:
    conn = get_conn()
    _AGG = (
        "COALESCE(SUM(tokens_in),0) AS ti, "
        "COALESCE(SUM(tokens_out),0) AS to_, "
        "COALESCE(SUM(cache_read_in),0) AS cr, "
        "COALESCE(SUM(cache_create_in),0) AS cc"
    )
    with LOCK:
        msg_row   = conn.execute(f"SELECT {_AGG} FROM messages").fetchone()
        rpt_row   = conn.execute(f"SELECT {_AGG} FROM reports").fetchone()
        api_row   = conn.execute(f"SELECT {_AGG} FROM api_calls").fetchone()
        by_model  = conn.execute(
            f"SELECT model, {_AGG} FROM api_calls GROUP BY model"
        ).fetchall()
        by_site   = conn.execute(
            f"SELECT call_site, {_AGG} FROM api_calls GROUP BY call_site "
            "ORDER BY ti + to_ DESC LIMIT 15"
        ).fetchall()
        by_day_msg = conn.execute(
            "SELECT DATE(datetime(created_at,'unixepoch')) AS d, "
            f"{_AGG} FROM messages GROUP BY d ORDER BY d DESC LIMIT 14"
        ).fetchall()
        by_day_rpt = conn.execute(
            "SELECT DATE(datetime(created_at,'unixepoch')) AS d, "
            f"{_AGG} FROM reports GROUP BY d ORDER BY d DESC LIMIT 14"
        ).fetchall()
        by_day_api = conn.execute(
            "SELECT DATE(datetime(created_at,'unixepoch')) AS d, "
            f"{_AGG} FROM api_calls GROUP BY d ORDER BY d DESC LIMIT 14"
        ).fetchall()

    def _src(row): return _row_usd(row)

    msg_s = _src(msg_row)
    rpt_s = _src(rpt_row)
    api_s = _src(api_row)

    ti  = msg_s["tokens_in"]  + rpt_s["tokens_in"]  + api_s["tokens_in"]
    to_ = msg_s["tokens_out"] + rpt_s["tokens_out"] + api_s["tokens_out"]
    cr  = msg_s["cache_read"] + rpt_s["cache_read"] + api_s["cache_read"]
    cc  = msg_s["cache_write"]+ rpt_s["cache_write"]+ api_s["cache_write"]
    total_usd = round(_compute_cost(ti, to_, cr, cc), 4)

    # Merge daily rows across tables
    day_map: dict[str, dict] = {}
    for rows in (by_day_msg, by_day_rpt, by_day_api):
        for row in rows:
            d = row["d"] or "unknown"
            if d not in day_map:
                day_map[d] = {"date": d, "tokens_in": 0, "tokens_out": 0,
                              "cache_read": 0, "cache_write": 0, "usd": 0.0}
            day_map[d]["tokens_in"]  += row["ti"] or 0
            day_map[d]["tokens_out"] += row["to_"] or 0
            day_map[d]["cache_read"] += row["cr"] or 0
            day_map[d]["cache_write"]+= row["cc"] or 0
    for entry in day_map.values():
        entry["usd"] = round(_compute_cost(
            entry["tokens_in"], entry["tokens_out"],
            entry["cache_read"], entry["cache_write"]), 4)
    by_day = sorted(day_map.values(), key=lambda x: x["date"], reverse=True)[:14]

    model_rows = []
    for row in by_model:
        d = _row_usd(row)
        d["model"] = row["model"] or "unknown"
        model_rows.append(d)
    model_rows.sort(key=lambda x: x["usd"], reverse=True)

    site_rows = []
    for row in by_site:
        d = _row_usd(row)
        d["call_site"] = row["call_site"] or "unknown"
        site_rows.append(d)
    site_rows.sort(key=lambda x: x["usd"], reverse=True)

    # Cache savings: what prompt caching saved vs. paying full input price
    cache_saved_usd = round(cr * (3.00 - 0.30) / 1_000_000, 4)

    return JSONResponse({
        "total_usd": total_usd,
        "tokens_in": ti,
        "tokens_out": to_,
        "cache_read": cr,
        "cache_write": cc,
        "cache_saved_usd": cache_saved_usd,
        "by_source": {
            "messages": msg_s,
            "reports": rpt_s,
            "api_calls": api_s,
        },
        "by_model": model_rows,
        "top_call_sites": site_rows,
        "by_day": by_day,
    })


@router.get("/usage", response_class=HTMLResponse)
def usage_page(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request=request,
        name="usage.html",
        context={"state": state},
    )
