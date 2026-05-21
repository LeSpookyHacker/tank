"""CRUD for `messages`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def append(*, conversation_id: str, role: str,
           content: list | dict | str,
           redacted_view: str | None = None,
           display_view: str | None = None,
           citations: list | None = None,
           tokens_in: int | None = None,
           tokens_out: int | None = None,
           cache_read_in: int | None = None,
           cache_create_in: int | None = None) -> str:
    mid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        next_ord = conn.execute(
            "SELECT COALESCE(MAX(ordinal), -1) + 1 AS n "
            "FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()["n"]
        conn.execute(
            "INSERT INTO messages "
            "(id, conversation_id, ordinal, role, content_json, "
            " redacted_view, display_view, tokens_in, tokens_out, "
            " cache_read_in, cache_create_in, citations_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, conversation_id, next_ord, role,
             json.dumps(content) if not isinstance(content, str) else content,
             redacted_view, display_view,
             tokens_in, tokens_out, cache_read_in, cache_create_in,
             json.dumps(citations or []), time.time()),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.time(), conversation_id),
        )
    return mid


def list_for_conv(conversation_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY ordinal",
        (conversation_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get(message_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    return dict(row) if row else None
