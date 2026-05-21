"""CRUD for ingested / manual meetings.

The `meetings` table is populated by the ICS watcher (Phase 11) and
manual entries from the UI. The auto-briefs scheduler tick reads from
`list_between(start, end)` to pre-generate meeting_prep briefs for
tomorrow's meetings.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, title: str, starts_at: float, ends_at: float | None = None,
           attendees: list[str] | None = None,
           external_id: str | None = None,
           source: str = "manual") -> str:
    mid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO meetings "
            "(id, external_id, title, starts_at, ends_at, "
            " attendees_json, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, external_id, title, starts_at, ends_at,
             json.dumps(attendees or []), source, time.time()),
        )
    return mid


def get(meeting_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM meetings WHERE id = ?", (meeting_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_between(start: float, end: float) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM meetings WHERE starts_at >= ? AND starts_at <= ? "
        "ORDER BY starts_at",
        (start, end),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def upcoming(within_hours: int = 24) -> list[dict]:
    now = time.time()
    return list_between(now, now + within_hours * 3600)


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["attendees"] = json.loads(d.get("attendees_json") or "[]")
    except Exception:
        d["attendees"] = []
    return d
