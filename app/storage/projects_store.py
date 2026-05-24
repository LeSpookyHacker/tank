from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn


def create_project(name: str, description: str = "", emoji: str = "🔐") -> str:
    pid = uuid.uuid4().hex[:12]
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO projects (id, name, description, emoji, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, name.strip(), description.strip(), emoji, time.time()),
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
