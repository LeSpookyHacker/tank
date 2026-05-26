# teams.py — REST API for team management.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage import projects_store, teams_store

router = APIRouter(prefix="/api/teams")


class CreateTeam(BaseModel):
    name: str
    description: str = ""
    color: str = "#6c5ce7"
    icon: str = "🛡️"


class UpdateTeam(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


@router.get("")
def list_teams(archived: bool = False) -> dict:
    teams = teams_store.list_teams(include_archived=archived)
    for t in teams:
        t.update(teams_store.get_team_stats(t["id"]))
    return {"teams": teams}


@router.post("")
def create_team(body: CreateTeam) -> dict:
    if not body.name.strip():
        raise HTTPException(400, "Team name is required.")
    tid = teams_store.insert_team(
        name=body.name,
        description=body.description,
        color=body.color,
        icon=body.icon,
    )
    return {"id": tid}


@router.patch("/{team_id}")
def update_team(team_id: str, body: UpdateTeam) -> dict:
    if not teams_store.get_team(team_id):
        raise HTTPException(404, "Team not found.")
    teams_store.update_team(team_id, **body.dict(exclude_none=True))
    return {"ok": True}


@router.post("/{team_id}/archive")
def archive_team(team_id: str) -> dict:
    if not teams_store.get_team(team_id):
        raise HTTPException(404, "Team not found.")
    teams_store.archive_team(team_id)
    return {"ok": True}


@router.get("/{team_id}/projects")
def list_team_projects(team_id: str, archived: bool = False) -> dict:
    if not teams_store.get_team(team_id):
        raise HTTPException(404, "Team not found.")
    ps = projects_store.list_by_team(team_id, include_archived=archived)
    return {"projects": ps}


@router.get("/{team_id}/stats")
def team_stats(team_id: str) -> dict:
    if not teams_store.get_team(team_id):
        raise HTTPException(404, "Team not found.")
    return teams_store.get_team_stats(team_id)
