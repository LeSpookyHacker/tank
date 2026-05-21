"""CRUD for `journal_entries`."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta

from app.db import LOCK, get_conn
from app.role import tenure_day


def _today_label() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def upsert_for_today(*, body: str, body_redacted: str) -> str:
    """Insert or update today's journal entry."""
    label = _today_label()
    conn = get_conn()
    now = time.time()
    with LOCK:
        existing = conn.execute(
            "SELECT id FROM journal_entries WHERE date_label = ?", (label,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE journal_entries SET body = ?, body_redacted = ?, "
                "    created_at = ? WHERE id = ?",
                (body, body_redacted, now, existing["id"]),
            )
            return existing["id"]
        jid = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO journal_entries "
            "(id, body, body_redacted, date_label, tenure_day, "
            " extracted_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (jid, body, body_redacted, label, tenure_day(), "{}", now),
        )
    return jid


def get_today() -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM journal_entries WHERE date_label = ?",
        (_today_label(),),
    ).fetchone()
    return dict(row) if row else None


def list_recent(days: int = 14) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = get_conn().execute(
        "SELECT * FROM journal_entries WHERE date_label >= ? "
        "ORDER BY date_label DESC",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def for_week(date_label: str | None = None) -> list[dict]:
    """Return entries from the ISO week containing `date_label`
    (default: this week)."""
    target = (datetime.strptime(date_label, "%Y-%m-%d") if date_label
              else datetime.now())
    monday = target - timedelta(days=target.weekday())
    rows = get_conn().execute(
        "SELECT * FROM journal_entries "
        "WHERE date_label >= ? AND date_label <= ? "
        "ORDER BY date_label",
        (monday.strftime("%Y-%m-%d"),
         (monday + timedelta(days=6)).strftime("%Y-%m-%d")),
    ).fetchall()
    return [dict(r) for r in rows]


def set_extracted(journal_id: str, extracted: dict) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE journal_entries SET extracted_json = ? WHERE id = ?",
            (json.dumps(extracted), journal_id),
        )
