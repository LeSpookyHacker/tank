"""Durable last-fired markers for the cron-ish scheduler.

Replaces the in-memory `_LAST_FIRED` dict so that an uvicorn restart
(intentional or via systemd `Restart=on-failure`) doesn't re-fire jobs
already done today, and doesn't skip jobs that haven't fired yet.

`last_label` is the granularity of the job:
- daily jobs use YYYY-MM-DD (local)
- weekly jobs use YYYY-Www (ISO week, e.g. 2026-W21)
"""
from __future__ import annotations

import time

from app.db import LOCK, get_conn


def last_label(job_name: str) -> str | None:
    row = get_conn().execute(
        "SELECT last_label FROM scheduler_state WHERE job_name = ?",
        (job_name,),
    ).fetchone()
    return row["last_label"] if row else None


def mark_fired(job_name: str, label: str) -> None:
    """Record that `job_name` fired with bucket `label`.

    Idempotent: re-inserting the same label is a no-op.
    """
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO scheduler_state "
            "(job_name, last_fired_at, last_label) VALUES (?, ?, ?)",
            (job_name, time.time(), label),
        )


def has_fired(job_name: str, label: str) -> bool:
    return last_label(job_name) == label


def all_state() -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM scheduler_state ORDER BY job_name"
    ).fetchall()
    return [dict(r) for r in rows]
