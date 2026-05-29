# teams_store.py — CRUD for the teams table.
from __future__ import annotations

import re
import time
import uuid

from app.db import LOCK, get_conn

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def insert_team(
    name: str,
    description: str = "",
    color: str = "#6c5ce7",
    icon: str = "🛡️",
    org_id: str | None = None,
) -> str:
    if org_id is None:
        row = get_conn().execute(
            "SELECT id FROM organizations ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        org_id = row["id"] if row else "default"
    tid = uuid.uuid4().hex[:12]
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO teams (id, org_id, name, description, color, icon, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (tid, org_id, name.strip(), description.strip(), color, icon, int(time.time())),
        )
    return tid


def get_team(team_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM teams WHERE id = ?", (team_id,)
    ).fetchone()
    return dict(row) if row else None


def list_teams(include_archived: bool = False) -> list[dict]:
    conn = get_conn()
    if include_archived:
        rows = conn.execute(
            "SELECT * FROM teams ORDER BY created_at ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM teams WHERE status != 'archived' ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def update_team(team_id: str, **kwargs: str) -> None:
    allowed = {"name", "description", "color", "icon", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    for k in updates:
        if not _SAFE_IDENT.match(k):
            raise ValueError(f"update_team: invalid column name {k!r}")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [team_id]
    conn = get_conn()
    with LOCK:
        conn.execute(f"UPDATE teams SET {set_clause} WHERE id = ?", values)


def archive_team(team_id: str) -> None:
    update_team(team_id, status="archived")


def get_team_stats(team_id: str) -> dict:
    """Return project count, open followup count, and last activity timestamp."""
    conn = get_conn()
    project_count = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE team_id = ? AND status != 'archived'",
        (team_id,),
    ).fetchone()[0]
    last_activity = conn.execute(
        "SELECT MAX(last_activity_at) FROM projects WHERE team_id = ?",
        (team_id,),
    ).fetchone()[0]
    return {
        "project_count": project_count,
        "last_activity_at": last_activity,
    }
