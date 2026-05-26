# projects.py — REST API for project management (redesign: team-scoped hierarchy).
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage import projects_store

router = APIRouter()


class CreateProject(BaseModel):
    name: str
    description: str = ""
    emoji: str = "🔐"
    color: str = "#6366f1"
    notes: str = ""
    team_id: Optional[str] = None
    status: str = "active"
    tags: str = "[]"
    risk_level: str = "medium"
    icon: str = "📦"


class UpdateProject(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[str] = None
    risk_level: Optional[str] = None
    icon: Optional[str] = None
    team_id: Optional[str] = None


@router.get("/api/projects")
def list_projects(archived: bool = False) -> dict:
    active_id = projects_store.get_active_project_id()
    return {
        "projects": projects_store.list_projects(include_archived=archived),
        "active_id": active_id,
    }


@router.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found.")
    return p


@router.get("/api/projects/{project_id}/stats")
def project_stats(project_id: str) -> dict:
    if not projects_store.get_project(project_id):
        raise HTTPException(404, "Project not found.")
    return projects_store.get_project_stats(project_id)


@router.post("/api/projects")
def create_project(body: CreateProject) -> dict:
    if not body.name.strip():
        raise HTTPException(400, "Project name is required.")
    pid = projects_store.create_project(
        body.name, body.description, body.emoji, body.color, body.notes,
        team_id=body.team_id, status=body.status,
        tags=body.tags, risk_level=body.risk_level, icon=body.icon,
    )
    return {"id": pid}


@router.patch("/api/projects/{project_id}")
def update_project(project_id: str, body: UpdateProject) -> dict:
    if not projects_store.get_project(project_id):
        raise HTTPException(404, "Project not found.")
    projects_store.update_project(project_id, **body.dict(exclude_none=True))
    return {"ok": True}


@router.post("/api/projects/{project_id}/activate")
def activate_project(project_id: str) -> dict:
    if not projects_store.get_project(project_id):
        raise HTTPException(404, "Project not found.")
    projects_store.set_active_project_id(project_id)
    return {"active_id": project_id}


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    if project_id in ("default", "imported"):
        raise HTTPException(400, "Cannot delete a system project.")
    if not projects_store.get_project(project_id):
        raise HTTPException(404, "Project not found.")
    projects_store.delete_project(project_id)
    if projects_store.get_active_project_id() == project_id:
        projects_store.set_active_project_id("default")
    return {"ok": True}
