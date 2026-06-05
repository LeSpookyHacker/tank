# dashboard.py — Top-level navigation routes for the redesigned Tank.
# Handles: /, /dashboard, /teams/*, /teams/*/projects/*, /search, and
# the supporting API endpoints (/api/dashboard/stats, /api/activity, /api/search).
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import MODEL, TEMPLATES_DIR
from app.db import LOCK, get_conn
from app.role import get_state
from app.storage import conversations_store, projects_store
from app.storage import teams_store
from app.storage.organizations_store import get_org

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_TABS = ("overview", "ingest", "reports", "threats", "chat")


# ── HTML routes ──────────────────────────────────────────────────────────────

#
# NOTE: `/` is intentionally NOT defined here. It is served by
# `pages.py::home` (the personal "Today" companion home). `/dashboard`
# below is the org→team→project "Workspaces" console. Keeping the two
# distinct — and routing the front door to Today — is the deliberate
# front-door decision; do not re-add a `/` → `/dashboard` redirect.


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    state = get_state()
    if not state.onboarded:
        return RedirectResponse(url="/onboarding", status_code=302)
    org = get_org()
    teams = teams_store.list_teams()
    # Attach stats to each team.
    for t in teams:
        t.update(teams_store.get_team_stats(t["id"]))
    # Recent activity feed (last 10 project touches).
    conn = get_conn()
    with LOCK:
        activity_rows = conn.execute(
            "SELECT id, name, emoji, color, icon, last_activity_at "
            "FROM projects WHERE last_activity_at IS NOT NULL "
            "ORDER BY last_activity_at DESC LIMIT 10"
        ).fetchall()
    activity = [dict(r) for r in activity_rows]
    # Org-level stats.
    with LOCK:
        total_projects = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status != 'archived'"
        ).fetchone()[0]
        total_docs = conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]
        total_followups = conn.execute(
            "SELECT COUNT(*) FROM followups WHERE status = 'open'"
        ).fetchone()[0]
    stats = {
        "team_count": len(teams),
        "project_count": total_projects,
        "open_followups": total_followups,
        "doc_count": total_docs,
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "state": state,
            "org": org,
            "teams": teams,
            "stats": stats,
            "activity": activity,
        },
    )


@router.get("/teams/{team_id}", response_class=HTMLResponse)
def team_view(request: Request, team_id: str):
    state = get_state()
    team = teams_store.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found.")
    include_archived = request.query_params.get("archived") == "1"
    projects = projects_store.list_by_team(team_id, include_archived=include_archived)
    # Attach per-project stats.
    conn = get_conn()
    for p in projects:
        p["doc_count"] = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE project_id = ?", (p["id"],)
        ).fetchone()[0]
        p["report_count"] = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE project_id = ?", (p["id"],)
        ).fetchone()[0]
    return templates.TemplateResponse(
        request=request,
        name="team.html",
        context={
            "state": state,
            "team": team,
            "projects": projects,
            "include_archived": include_archived,
        },
    )


@router.get("/teams/{team_id}/projects/{project_id}", response_class=HTMLResponse)
def project_workspace(request: Request, team_id: str, project_id: str):
    return _project_workspace_response(request, team_id, project_id, "overview")


@router.get("/teams/{team_id}/projects/{project_id}/ingest", response_class=HTMLResponse)
def project_ingest(request: Request, team_id: str, project_id: str):
    return _project_workspace_response(request, team_id, project_id, "ingest")


@router.get("/teams/{team_id}/projects/{project_id}/reports", response_class=HTMLResponse)
def project_reports(request: Request, team_id: str, project_id: str):
    return _project_workspace_response(request, team_id, project_id, "reports")


@router.get("/teams/{team_id}/projects/{project_id}/threats", response_class=HTMLResponse)
def project_threats(request: Request, team_id: str, project_id: str):
    return _project_workspace_response(request, team_id, project_id, "threats")


@router.get("/teams/{team_id}/projects/{project_id}/chat", response_class=HTMLResponse)
def project_chat(request: Request, team_id: str, project_id: str):
    return _project_workspace_response(request, team_id, project_id, "chat")


def _project_workspace_response(request, team_id: str, project_id: str, tab: str):
    state = get_state()
    team = teams_store.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found.")
    project = projects_store.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    if project.get("team_id") != team_id:
        raise HTTPException(404, "Project does not belong to this team.")

    stats = projects_store.get_project_stats(project_id)
    conn = get_conn()

    # Recent documents for overview and ingest tabs.
    recent_docs = [dict(r) for r in conn.execute(
        "SELECT id, title, source_path, category, ingested_at FROM documents "
        "WHERE project_id = ? ORDER BY ingested_at DESC LIMIT 20",
        (project_id,),
    ).fetchall()]

    # Recent reports for reports tab.
    recent_reports = [dict(r) for r in conn.execute(
        "SELECT id, kind, title, created_at FROM reports "
        "WHERE project_id = ? ORDER BY created_at DESC LIMIT 20",
        (project_id,),
    ).fetchall()]

    # DFD analyses for threats tab.
    from app.storage import dfd_store
    recent_dfds = dfd_store.list_recent(limit=20)
    # Flatten threats from all DFDs for this project (project_id stored on dfd row when set).
    all_threats = []
    for dfd in recent_dfds:
        analysis = dfd.get("analysis", {}) if isinstance(dfd.get("analysis"), dict) else {}
        for t in analysis.get("threats", []):
            t = dict(t)
            t["dfd_id"] = dfd["id"]
            t["dfd_created_at"] = dfd.get("created_at")
            t.setdefault("status", "open")
            all_threats.append(t)

    # Chat: find or create project conversation.
    conv_id = None
    messages = []
    if tab == "chat":
        conv_id = conversations_store.get_or_create_for_project(
            project_id, state.role_mode.value, MODEL
        )
        from app.storage import messages_store
        messages = messages_store.list_for_conv(conv_id)

    # Followups for overview tab.
    open_followups = [dict(r) for r in conn.execute(
        "SELECT * FROM followups WHERE status = 'open' ORDER BY due_at ASC LIMIT 10"
    ).fetchall()]

    return templates.TemplateResponse(
        request=request,
        name="project_workspace.html",
        context={
            "state": state,
            "team": team,
            "project": project,
            "active_tab": tab,
            "stats": stats,
            "recent_docs": recent_docs,
            "recent_reports": recent_reports,
            "all_threats": all_threats,
            "conv_id": conv_id,
            "messages": messages,
            "open_followups": open_followups,
        },
    )


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request):
    state = get_state()
    q = request.query_params.get("q", "").strip()
    results = {}
    if q:
        results = _do_search(q)
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"state": state, "q": q, "results": results},
    )


# ── API endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/dashboard/stats")
def dashboard_stats() -> JSONResponse:
    conn = get_conn()
    with LOCK:
        team_count = conn.execute(
            "SELECT COUNT(*) FROM teams WHERE status != 'archived'"
        ).fetchone()[0]
        project_count = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status != 'archived'"
        ).fetchone()[0]
        doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        followup_count = conn.execute(
            "SELECT COUNT(*) FROM followups WHERE status = 'open'"
        ).fetchone()[0]
    return JSONResponse({
        "team_count": team_count,
        "project_count": project_count,
        "doc_count": doc_count,
        "open_followups": followup_count,
    })


@router.get("/api/activity")
def activity_feed(limit: int = 10) -> JSONResponse:
    conn = get_conn()
    with LOCK:
        rows = conn.execute(
            "SELECT id, name, emoji, color, icon, team_id, last_activity_at "
            "FROM projects WHERE last_activity_at IS NOT NULL "
            "ORDER BY last_activity_at DESC LIMIT ?",
            (min(limit, 50),),
        ).fetchall()
    return JSONResponse({"activity": [dict(r) for r in rows]})


@router.get("/api/search")
def search_api(q: str = "") -> JSONResponse:
    q = q.strip()
    if not q:
        return JSONResponse({"results": {}})
    return JSONResponse({"results": _do_search(q)})


def _do_search(q: str) -> dict:
    if not q or len(q) > 200:
        return {"teams": [], "projects": [], "documents": [], "reports": []}
    conn = get_conn()
    q_like = f"%{q}%"

    teams = [dict(r) for r in conn.execute(
        "SELECT id, name, description, color, icon FROM teams "
        "WHERE (name LIKE ? OR description LIKE ?) AND status != 'archived' LIMIT 10",
        (q_like, q_like),
    ).fetchall()]

    projects = [dict(r) for r in conn.execute(
        "SELECT id, name, description, emoji, color, team_id FROM projects "
        "WHERE (name LIKE ? OR description LIKE ? OR tags LIKE ?) "
        "AND status != 'archived' LIMIT 20",
        (q_like, q_like, q_like),
    ).fetchall()]

    documents = [dict(r) for r in conn.execute(
        "SELECT id, title, category, source_path, project_id FROM documents "
        "WHERE title LIKE ? LIMIT 20",
        (q_like,),
    ).fetchall()]

    reports = [dict(r) for r in conn.execute(
        "SELECT id, kind, title, project_id FROM reports "
        "WHERE title LIKE ? LIMIT 10",
        (q_like,),
    ).fetchall()]

    return {
        "teams": teams,
        "projects": projects,
        "documents": documents,
        "reports": reports,
    }
