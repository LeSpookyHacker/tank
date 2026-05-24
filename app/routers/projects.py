from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import projects_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateProject(BaseModel):
    name: str
    description: str = ""
    emoji: str = "🔐"


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
    pid = projects_store.create_project(body.name, body.description, body.emoji)
    return {"id": pid}


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
