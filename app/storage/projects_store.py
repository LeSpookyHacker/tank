# projects_store.py — CRUD for the projects table.
# Phase 1 (tankinstuction): added color and notes fields; added update_project().
from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn


def create_project(
    name: str,
    description: str = "",
    emoji: str = "🔐",
    color: str = "#6366f1",
    notes: str = "",
) -> str:
    pid = uuid.uuid4().hex[:12]
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO projects (id, name, description, emoji, color, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, name.strip(), description.strip(), emoji, color, notes, time.time()),
        )
    return pid


def list_projects() -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM projects ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    return dict(row) if row else None


def update_project(project_id: str, **kwargs: str) -> None:
    """Patch one or more fields on a project row."""
    allowed = {"name", "description", "emoji", "color", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]
    conn = get_conn()
    with LOCK:
        conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)


def delete_project(project_id: str) -> None:
    if project_id == "default":
        raise ValueError("Cannot delete the Default project.")
    conn = get_conn()
    with LOCK:
        # Null out project_id on owned rows rather than cascade-deleting them.
        for table in ("documents", "conversations", "reports",
                      "threat_models", "design_reviews", "postmortems_drafts", "tabletops"):
            conn.execute(
                f"UPDATE {table} SET project_id = 'default' WHERE project_id = ?",
                (project_id,),
            )
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def get_active_project_id() -> str:
    row = get_conn().execute(
        "SELECT active_project_id FROM app_state WHERE id = 1"
    ).fetchone()
    if row and row["active_project_id"]:
        return row["active_project_id"]
    return "default"


def set_active_project_id(project_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE app_state SET active_project_id = ? WHERE id = 1",
            (project_id,),
        )
