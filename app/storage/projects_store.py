# projects_store.py — CRUD for the projects table.
# Redesign: added team_id, org_id, status, tags, risk_level, icon, last_activity_at.
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
    team_id: str | None = None,
    org_id: str | None = None,
    status: str = "active",
    tags: str = "[]",
    risk_level: str = "medium",
    icon: str = "📦",
) -> str:
    # Resolve team/org if not provided.
    if team_id is None:
        row = get_conn().execute(
            "SELECT id, org_id FROM teams ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row:
            team_id, org_id = row["id"], row["org_id"]
    pid = uuid.uuid4().hex[:12]
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO projects "
            "(id, name, description, emoji, color, notes, team_id, org_id, "
            " status, tags, risk_level, icon, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pid, name.strip(), description.strip(), emoji, color, notes,
                team_id, org_id, status, tags, risk_level, icon, time.time(),
            ),
        )
    return pid


def list_projects(include_archived: bool = False) -> list[dict]:
    conn = get_conn()
    if include_archived:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM projects WHERE status != 'archived' ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_by_team(team_id: str, include_archived: bool = False) -> list[dict]:
    conn = get_conn()
    if include_archived:
        rows = conn.execute(
            "SELECT * FROM projects WHERE team_id = ? ORDER BY last_activity_at DESC, created_at DESC",
            (team_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM projects WHERE team_id = ? AND status != 'archived' "
            "ORDER BY last_activity_at DESC, created_at DESC",
            (team_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    return dict(row) if row else None


def update_project(project_id: str, **kwargs) -> None:
    allowed = {"name", "description", "emoji", "color", "notes",
               "status", "tags", "risk_level", "icon", "team_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]
    conn = get_conn()
    with LOCK:
        conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)


def touch_activity(project_id: str) -> None:
    """Update last_activity_at to now for a project."""
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE projects SET last_activity_at = ? WHERE id = ?",
            (int(time.time()), project_id),
        )


def delete_project(project_id: str) -> None:
    if project_id in ("default", "imported"):
        raise ValueError("Cannot delete a system project.")
    conn = get_conn()
    with LOCK:
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


def get_project_stats(project_id: str) -> dict:
    """Return document, report, threat model, and open followup counts for a project."""
    conn = get_conn()
    doc_count = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    report_count = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    tm_count = conn.execute(
        "SELECT COUNT(*) FROM threat_models WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    conv_count = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    followup_count = conn.execute(
        "SELECT COUNT(*) FROM followups WHERE status = 'open'"
    ).fetchone()[0]
    return {
        "doc_count": doc_count,
        "report_count": report_count,
        "tm_count": tm_count,
        "conv_count": conv_count,
        "open_followups": followup_count,
    }
