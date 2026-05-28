"""CRUD for intake_interview — the first-hire quick-start interview."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def create() -> str:
    iid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO intake_interview (id, created_at, answers, kb_seeded) "
            "VALUES (?, ?, '{}', 0)",
            (iid, now),
        )
    return iid


def get_latest() -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM intake_interview ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["answers"] = json.loads(d.get("answers") or "{}")
    except Exception:
        d["answers"] = {}
    return d


def complete(interview_id: str, answers: dict) -> None:
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE intake_interview "
            "SET completed_at = ?, answers = ? "
            "WHERE id = ?",
            (now, json.dumps(answers), interview_id),
        )


def mark_seeded(interview_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE intake_interview SET kb_seeded = 1 WHERE id = ?",
            (interview_id,),
        )
