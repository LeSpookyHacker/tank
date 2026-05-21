"""CRUD for user-tracked follow-ups."""
from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn


def create(*, title: str, body: str | None = None,
           source_kind: str = "user",
           source_id: str | None = None,
           related_entity_id: str | None = None,
           due_at: float | None = None) -> str:
    fid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO followups "
            "(id, title, body, status, due_at, source_kind, source_id, "
            " related_entity_id, created_at, updated_at) "
            "VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)",
            (fid, title, body, due_at, source_kind, source_id,
             related_entity_id, now, now),
        )
    return fid


def list_by_status(status: str = "open", limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM followups WHERE status = ? "
        "ORDER BY due_at IS NULL, due_at, created_at "
        "LIMIT ?",
        (status, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_due_today() -> list[dict]:
    import time as _time
    cutoff = _time.time() + 86400
    rows = get_conn().execute(
        "SELECT * FROM followups WHERE status = 'open' "
        "AND due_at IS NOT NULL AND due_at <= ? "
        "ORDER BY due_at",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def set_status(followup_id: str, status: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE followups SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), followup_id),
        )


def get(followup_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM followups WHERE id = ?", (followup_id,)
    ).fetchone()
    return dict(row) if row else None
