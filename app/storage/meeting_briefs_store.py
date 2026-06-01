"""CRUD for `meeting_briefs` — nightly auto-generated batch briefs.

Populated by the `meeting_prep.batch_handler` after a scheduler-fired
batch lands. The interactive `POST /api/meeting-prep` route returns its
dict directly and does NOT write here — its caller already has the
result in hand.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, meeting_id: str, brief: dict) -> str:
    """Persist a rehydrated brief dict. Returns the row id."""
    bid = uuid.uuid4().hex
    with LOCK:
        get_conn().execute(
            "INSERT INTO meeting_briefs (id, meeting_id, brief_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (bid, meeting_id, json.dumps(brief), time.time()),
        )
    return bid


def latest_for_meeting(meeting_id: str) -> dict | None:
    """Most recent brief for a given meeting, or None."""
    row = get_conn().execute(
        "SELECT id, meeting_id, brief_json, created_at "
        "FROM meeting_briefs WHERE meeting_id = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (meeting_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "meeting_id": row["meeting_id"],
        "brief": json.loads(row["brief_json"]),
        "created_at": row["created_at"],
    }


def list_recent(limit: int = 20) -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, meeting_id, brief_json, created_at "
        "FROM meeting_briefs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "meeting_id": r["meeting_id"],
            "brief": json.loads(r["brief_json"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
