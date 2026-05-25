# projects.py — Routes for project management.
# Phase 1 (tankinstuction): CreateProject now includes color and notes.
# Phase 2 (tankinstuction): Added /projects/{id} detail page and PATCH /api/projects/{id}.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.db import LOCK, get_conn
from app.role import get_state
from app.storage import projects_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateProject(BaseModel):
    name: str
    description: str = ""
    emoji: str = "🔐"
    color: str = "#6366f1"
    notes: str = ""


class UpdateProject(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None


@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request):
    state = get_state()
    project_list = projects_store.list_projects()
    active_id = projects_store.get_active_project_id()
    return templates.TemplateResponse(
        request=request,
        name="projects.html",
        context={"state": state, "projects": project_list, "active_id": active_id},
    )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(request: Request, project_id: str):
    project = projects_store.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    state = get_state()
    conn = get_conn()
    doc_count = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    conv_count = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    report_count = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    recent_docs = conn.execute(
        "SELECT id, source_path, category, ingested_at FROM documents "
        "WHERE project_id = ? ORDER BY ingested_at DESC LIMIT 5",
        (project_id,),
    ).fetchall()
    recent_convs = conn.execute(
        "SELECT id, title, updated_at FROM conversations "
        "WHERE project_id = ? ORDER BY updated_at DESC LIMIT 5",
        (project_id,),
    ).fetchall()
    return templates.TemplateResponse(
        request=request,
        name="project_detail.html",
        context={
            "state": state,
            "project": project,
            "doc_count": doc_count,
            "conv_count": conv_count,
            "report_count": report_count,
            "recent_docs": [dict(r) for r in recent_docs],
            "recent_convs": [dict(r) for r in recent_convs],
        },
    )


@router.get("/api/projects")
def list_projects() -> dict:
    active_id = projects_store.get_active_project_id()
    return {
        "projects": projects_store.list_projects(),
        "active_id": active_id,
    }


@router.post("/api/projects")
def create_project(body: CreateProject) -> dict:
    if not body.name.strip():
        raise HTTPException(400, "Project name is required.")
    pid = projects_store.create_project(
        body.name, body.description, body.emoji, body.color, body.notes
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
    if project_id == "default":
        raise HTTPException(400, "Cannot delete the Default project.")
    if not projects_store.get_project(project_id):
        raise HTTPException(404, "Project not found.")
    projects_store.delete_project(project_id)
    # If we just deleted the active project, fall back to default.
    if projects_store.get_active_project_id() == project_id:
        projects_store.set_active_project_id("default")
    return {"ok": True}
