"""CRUD for `dfd_analyses`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, diagram_hash: str, mermaid_src: str | None,
           analysis_json: dict,
           tokens_in: int | None = None,
           tokens_out: int | None = None) -> str:
    did = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO dfd_analyses "
            "(id, diagram_hash, mermaid_src, analysis_json, tokens_in, tokens_out, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (did, diagram_hash, mermaid_src,
             json.dumps(analysis_json), tokens_in, tokens_out, time.time()),
        )
    return did


def get_by_hash(diagram_hash: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM dfd_analyses WHERE diagram_hash = ?", (diagram_hash,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["analysis"] = json.loads(d.pop("analysis_json", "{}"))
    return d


def get(dfd_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM dfd_analyses WHERE id = ?", (dfd_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["analysis"] = json.loads(d.pop("analysis_json", "{}"))
    return d


def list_recent(limit: int = 20) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM dfd_analyses ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["analysis"] = json.loads(d.pop("analysis_json", "{}"))
        result.append(d)
    return result
