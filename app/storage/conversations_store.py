"""CRUD for `conversations`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def create(*, role_mode: str, model: str,
           title: str | None = None,
           scope: dict | None = None,
           project_id: str | None = None) -> str:
    cid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO conversations "
            "(id, title, role_mode, model, scope_json, project_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, title, role_mode, model,
             json.dumps(scope or {}), project_id, now, now),
        )
    return cid


def get(conv_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    return dict(row) if row else None


def list_recent(limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_or_create_empty(*, role_mode: str, model: str) -> str:
    """Return the ID of an existing empty, untitled conversation to reuse,
    or create a fresh one.

    'Empty' means: no title set AND zero messages. This is the canonical
    'scratch' conversation the side panel attaches to. A user creating a
    named chat (via the full /chat page) never touches this path, so their
    named conversations are left alone.
    """
    conn = get_conn()
    # Look for the most-recently-updated conversation that is untitled and
    # has no messages. JOIN is cheaper than a subquery on indexed columns.
    row = conn.execute(
        """
        SELECT c.id FROM conversations c
        WHERE c.title IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM messages m WHERE m.conversation_id = c.id
          )
        ORDER BY c.updated_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row:
        return row["id"]
    return create(role_mode=role_mode, model=model)


def list_by_project(project_id: str, limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
        (project_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_or_create_for_project(project_id: str, role_mode: str, model: str) -> str:
    """Return the most-recent conversation for a project, creating one if none exists."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM conversations WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row:
        return row["id"]
    return create(role_mode=role_mode, model=model,
                  title=None, project_id=project_id)


def delete(conv_id: str) -> None:
    with LOCK:
        get_conn().execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


def touch(conv_id: str, title: str | None = None) -> None:
    conn = get_conn()
    with LOCK:
        if title:
            conn.execute(
                "UPDATE conversations SET updated_at = ?, title = ? "
                "WHERE id = ?",
                (time.time(), title, conv_id),
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (time.time(), conv_id),
            )
