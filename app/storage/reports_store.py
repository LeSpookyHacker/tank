"""CRUD for `reports`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, kind: str, title: str, content_md: str,
           content_md_redacted: str, role_mode: str, model: str,
           scope: dict | None = None,
           tokens_in: int | None = None,
           tokens_out: int | None = None,
           cache_read_in: int | None = None,
           cache_create_in: int | None = None) -> str:
    rid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO reports "
            "(id, kind, scope_json, role_mode, model, title, "
            " content_md, content_md_redacted, tokens_in, tokens_out, "
            " cache_read_in, cache_create_in, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, kind, json.dumps(scope or {}), role_mode, model,
             title, content_md, content_md_redacted,
             tokens_in, tokens_out, cache_read_in, cache_create_in,
             time.time()),
        )
    return rid


def get(report_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    return dict(row) if row else None


def list_by_kind(kind: str | None = None, limit: int = 100) -> list[dict]:
    if kind:
        rows = get_conn().execute(
            "SELECT * FROM reports WHERE kind = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def latest_for_kind(kind: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM reports WHERE kind = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (kind,),
    ).fetchone()
    return dict(row) if row else None


def latest_two_for_kind(kind: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM reports WHERE kind = ? "
        "ORDER BY created_at DESC LIMIT 2",
        (kind,),
    ).fetchall()
    return [dict(r) for r in rows]
