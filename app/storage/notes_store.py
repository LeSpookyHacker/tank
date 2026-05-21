"""CRUD for `notes`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, body: str, body_redacted: str,
           meeting_with_entity_id: str | None = None) -> str:
    nid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO notes "
            "(id, body, body_redacted, meeting_with_entity_id, "
            " extracted_json, confirmed, created_at) "
            "VALUES (?, ?, ?, ?, '{}', 0, ?)",
            (nid, body, body_redacted, meeting_with_entity_id, now),
        )
    return nid


def update_extracted(note_id: str, extracted: dict) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE notes SET extracted_json = ? WHERE id = ?",
            (json.dumps(extracted), note_id),
        )


def mark_confirmed(note_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE notes SET confirmed = 1 WHERE id = ?", (note_id,),
        )


def get(note_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    return dict(row) if row else None


def list_recent(limit: int = 30) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM notes ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
