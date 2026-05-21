"""CRUD for the lessons-learned database.

A lesson is a 1-2-paragraph distillation of something the team or
engineer learned. It comes from postmortems, tabletops, design
reviews, or user-promoted journal entries. Indexed by tags and by
free-text search for chat retrieval.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def create(*, title: str, body_md: str,
           body_md_redacted: str | None = None,
           source_kind: str, source_id: str,
           tags: list[str] | None = None,
           scope_entity_ids: list[str] | None = None) -> str:
    lid = uuid.uuid4().hex
    body_red = body_md_redacted if body_md_redacted is not None else body_md
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO lessons "
            "(id, title, body_md, body_md_redacted, source_kind, "
            " source_id, tags, scope_entity_ids, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lid, title, body_md, body_red, source_kind, source_id,
             json.dumps(tags or []),
             json.dumps(scope_entity_ids or []),
             time.time()),
        )
    return lid


def get(lesson_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM lessons WHERE id = ?", (lesson_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_recent(days: int = 90, limit: int = 100) -> list[dict]:
    cutoff = time.time() - days * 86400
    rows = get_conn().execute(
        "SELECT * FROM lessons WHERE captured_at >= ? "
        "ORDER BY captured_at DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def search(query: str, tag: str | None = None,
           limit: int = 25) -> list[dict]:
    """Naive LIKE search across title + body. FTS index could come later."""
    q = f"%{query.lower()}%"
    if tag:
        rows = get_conn().execute(
            "SELECT * FROM lessons "
            "WHERE (LOWER(title) LIKE ? OR LOWER(body_md_redacted) LIKE ?) "
            "AND tags LIKE ? "
            "ORDER BY captured_at DESC LIMIT ?",
            (q, q, f'%"{tag}"%', limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM lessons "
            "WHERE LOWER(title) LIKE ? OR LOWER(body_md_redacted) LIKE ? "
            "ORDER BY captured_at DESC LIMIT ?",
            (q, q, limit),
        ).fetchall()
    return [_hydrate(r) for r in rows]


def list_by_tag(tag: str, limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM lessons WHERE tags LIKE ? "
        "ORDER BY captured_at DESC LIMIT ?",
        (f'%"{tag}"%', limit),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except Exception:
        d["tags"] = []
    try:
        d["scope_entity_ids"] = json.loads(d.get("scope_entity_ids") or "[]")
    except Exception:
        d["scope_entity_ids"] = []
    return d
