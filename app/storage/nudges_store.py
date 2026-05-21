"""CRUD for `nudges`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, kind: str, title: str, body: str,
           payload: dict | None = None,
           priority: int = 50) -> str:
    nid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO nudges "
            "(id, kind, title, body, payload_json, priority, status, "
            " snoozed_until, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, ?, ?)",
            (nid, kind, title, body, json.dumps(payload or {}),
             priority, now, now),
        )
    return nid


def list_open(limit: int = 50) -> list[dict]:
    now = time.time()
    rows = get_conn().execute(
        "SELECT * FROM nudges "
        "WHERE status = 'open' "
        "  AND (snoozed_until IS NULL OR snoozed_until <= ?) "
        "ORDER BY priority DESC, created_at DESC LIMIT ?",
        (now, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def set_status(nudge_id: str, status: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE nudges SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), nudge_id),
        )


def snooze(nudge_id: str, until_ts: float) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE nudges SET status = 'snoozed', snoozed_until = ?, "
            "    updated_at = ? WHERE id = ?",
            (until_ts, time.time(), nudge_id),
        )


def count_open_today() -> int:
    cutoff = time.time() - 86400
    row = get_conn().execute(
        "SELECT COUNT(*) AS n FROM nudges "
        "WHERE created_at >= ? AND status = 'open'",
        (cutoff,),
    ).fetchone()
    return row["n"] if row else 0
