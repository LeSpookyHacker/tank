"""Org Discovery Wizard — guided workflow for first-hire org inventory.

Step 1: GitHub org scan (enumerate repos, suggest which to ingest)
Step 2: Team directory import (CSV upload → PersonEntity + TeamEntity stubs)
Step 3: Manual service entry (structured form)
Step 4: Summary + ingestion queue

Routes:
  GET  /discovery                     — wizard UI
  POST /api/discovery/github-scan     — enumerate GitHub org repos
  POST /api/discovery/team-import     — parse CSV, return preview rows
  POST /api/discovery/confirm         — create entity stubs from selections
"""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import entities_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.discovery")

# Non-service repo name patterns to de-prioritize
_NON_SERVICE_PATTERNS = (
    "-docs", "-config", "-terraform", "-infra", "-scripts",
    "-ci", "-deploy", "-helm", ".github", "dotfiles",
)

_90_DAYS_SECS = 90 * 86400


class GithubScanBody(BaseModel):
    org: str
    token: str


class ConfirmSelections(BaseModel):
    repos: list[dict] = []          # [{name, action: "ingest"|"stub"|"skip"}]
    teams: list[dict] = []          # [{name, email, team, role}]
    services: list[dict] = []       # [{name, type, team, stack, notes}]


# ── Page ──────────────────────────────────────────────────────────────────────

@router.get("/discovery", response_class=HTMLResponse)
def discovery_page(request: Request):
    state = get_state()
    return templates.TemplateResponse(
        request=request,
        name="discovery.html",
        context={"state": state},
    )


# ── API ───────────────────────────────────────────────────────────────────────

@router.post("/api/discovery/github-scan")
async def github_scan(body: GithubScanBody) -> JSONResponse:
    """Enumerate repositories in a GitHub org using a personal access token."""
    try:
        import httpx
    except ImportError:
        return JSONResponse({"error": "httpx not installed"}, status_code=500)

    org = body.org.strip().strip("/")
    if not org or "/" in org:
        return JSONResponse({"error": "invalid org name"}, status_code=422)

    repos = []
    page = 1
    cutoff = time.time() - _90_DAYS_SECS

    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            resp = await client.get(
                f"https://api.github.com/orgs/{org}/repos",
                headers={
                    "Authorization": f"Bearer {body.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                params={"per_page": 100, "page": page, "type": "all"},
            )
            if resp.status_code == 401:
                return JSONResponse({"error": "Invalid token"}, status_code=401)
            if resp.status_code == 404:
                return JSONResponse({"error": f"Org '{org}' not found"}, status_code=404)
            if not resp.is_success:
                return JSONResponse({"error": f"GitHub API error: {resp.status_code}"}, status_code=502)

            batch = resp.json()
            if not batch:
                break

            for r in batch:
                pushed = r.get("pushed_at") or ""
                try:
                    pushed_ts = datetime.fromisoformat(
                        pushed.replace("Z", "+00:00")
                    ).timestamp()
                except Exception:
                    pushed_ts = 0

                is_archived = r.get("archived", False)
                name_lower = (r.get("name") or "").lower()
                recent = pushed_ts >= cutoff
                looks_like_service = (
                    not is_archived
                    and recent
                    and not any(name_lower.endswith(p) or name_lower.startswith(p.lstrip("-"))
                                for p in _NON_SERVICE_PATTERNS)
                )

                repos.append({
                    "name": r.get("name"),
                    "description": r.get("description") or "",
                    "language": r.get("language") or "Unknown",
                    "last_pushed": pushed,
                    "visibility": "public" if not r.get("private") else "private",
                    "archived": is_archived,
                    "recent": recent,
                    "suggested_action": "ingest" if looks_like_service else "stub",
                    "pre_checked": looks_like_service,
                })

            if len(batch) < 100:
                break
            page += 1

    return JSONResponse({"repos": repos, "total": len(repos)})


@router.post("/api/discovery/team-import")
async def team_import(file: UploadFile = File(...)) -> JSONResponse:
    """Parse a CSV file (columns: name, email, team, role) and return a preview."""
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        if i >= 500:
            break
        rows.append({
            "name": (row.get("name") or row.get("Name") or "").strip(),
            "email": (row.get("email") or row.get("Email") or "").strip(),
            "team": (row.get("team") or row.get("Team") or "").strip(),
            "role": (row.get("role") or row.get("Role") or "").strip(),
        })

    # Collect unique team names for merge suggestions
    teams = sorted({r["team"] for r in rows if r["team"]})
    return JSONResponse({"rows": rows, "teams": teams, "total": len(rows)})


@router.post("/api/discovery/confirm")
async def confirm_selections(body: ConfirmSelections) -> JSONResponse:
    """Create entity stubs from all confirmed selections."""
    created = {"repos": 0, "people": 0, "teams": 0, "services": 0}
    stub_base = {"stub_unconfirmed": True}

    # Repos
    for repo in body.repos:
        action = repo.get("action", "skip")
        name = (repo.get("name") or "").strip()
        if not name or action == "skip":
            continue
        entities_store.upsert_entity(
            type_="Repo",
            name=name,
            description=repo.get("description") or "",
            attrs={**stub_base, "stub_source": "org_discovery",
                   "language": repo.get("language"), "action": action},
            confidence=0.5,
            provenance="user",
        )
        created["repos"] += 1

    # Teams
    seen_teams: set[str] = set()
    for person in body.teams:
        pname = (person.get("name") or "").strip()
        team = (person.get("team") or "").strip()
        if pname:
            entities_store.upsert_entity(
                type_="Person",
                name=pname,
                attrs={**stub_base, "stub_source": "directory_import",
                       "email": person.get("email"),
                       "team": team, "role": person.get("role")},
                confidence=0.5,
                provenance="user",
            )
            created["people"] += 1
        if team and team not in seen_teams:
            entities_store.upsert_entity(
                type_="Person",
                name=team,
                attrs={**stub_base, "stub_source": "directory_import",
                       "kind": "team"},
                confidence=0.5,
                provenance="user",
            )
            seen_teams.add(team)
            created["teams"] += 1

    # Manually entered services
    for svc in body.services:
        name = (svc.get("name") or "").strip()
        if not name:
            continue
        entities_store.upsert_entity(
            type_="Service",
            name=name,
            description=svc.get("notes") or "",
            attrs={**stub_base, "stub_source": "manual_discovery",
                   "service_type": svc.get("type"),
                   "owning_team": svc.get("team"),
                   "tech_stack": svc.get("stack")},
            confidence=0.5,
            provenance="user",
        )
        created["services"] += 1

    return JSONResponse({"ok": True, "created": created})
