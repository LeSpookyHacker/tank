"""Lightweight usage-event logging.

Drives the "hot entities" widget and "abandoned threads" detection.
"""
from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn


def record(*, kind: str, entity_id: str | None = None,
           chunk_id: str | None = None,
           conversation_id: str | None = None,
           report_id: str | None = None) -> None:
    uid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO usage_events "
            "(id, kind, entity_id, chunk_id, conversation_id, "
            " report_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, kind, entity_id, chunk_id, conversation_id,
             report_id, time.time()),
        )


def hot_entities(days: int = 7, k: int = 5) -> list[dict]:
    """Top-k entities by event count over the last N days."""
    cutoff = time.time() - days * 86400
    rows = get_conn().execute(
        "SELECT entity_id, COUNT(*) AS n "
        "FROM usage_events "
        "WHERE entity_id IS NOT NULL AND created_at >= ? "
        "GROUP BY entity_id ORDER BY n DESC LIMIT ?",
        (cutoff, k),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        ent = get_conn().execute(
            "SELECT id, type, name FROM entities WHERE id = ?",
            (r["entity_id"],),
        ).fetchone()
        if ent:
            out.append({**dict(ent), "event_count": r["n"]})
    return out


def abandoned_conversations(days: int = 14) -> list[dict]:
    """Conversations with no usage events in the last N days."""
    cutoff = time.time() - days * 86400
    rows = get_conn().execute(
        "SELECT c.id, c.title, c.updated_at "
        "FROM conversations c "
        "WHERE c.updated_at < ? "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM usage_events u "
        "  WHERE u.conversation_id = c.id AND u.created_at >= ?"
        ") "
        "ORDER BY c.updated_at",
        (cutoff, cutoff),
    ).fetchall()
    return [dict(r) for r in rows]
