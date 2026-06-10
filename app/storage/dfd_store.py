"""CRUD for `dfd_analyses` — DFD & Threat Model revamp store."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(
    *,
    diagram_hash: str,
    mermaid_src: str | None,
    analysis_json: dict,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    input_format: str | None = None,
    project_id: str | None = None,
    cached: bool = False,
) -> str:
    did = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO dfd_analyses "
            "(id, diagram_hash, mermaid_src, analysis_json, tokens_in, tokens_out, "
            " input_format, project_id, cached, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                did, diagram_hash, mermaid_src,
                json.dumps(analysis_json), tokens_in, tokens_out,
                input_format, project_id, 1 if cached else 0, time.time(),
            ),
        )
    return did


def get_by_hash(diagram_hash: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM dfd_analyses WHERE diagram_hash = ?", (diagram_hash,)
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(dict(row))


def get(dfd_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM dfd_analyses WHERE id = ?", (dfd_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(dict(row))


def list_recent(limit: int = 20, project_id: str | None = None) -> list[dict]:
    if project_id:
        rows = get_conn().execute(
            "SELECT * FROM dfd_analyses WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM dfd_analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(dict(r)) for r in rows]


def _row_to_dict(d: dict) -> dict:
    d["analysis"] = json.loads(d.pop("analysis_json", "{}"))
    d["cached"] = bool(d.get("cached", 0))

    # Extract title from Mermaid source
    title = d["analysis"].get("title")
    if not title:
        import re
        mermaid_src = d.get("mermaid_src") or d["analysis"].get("annotated_mermaid") or ""
        match = re.search(r'title:?\s*(.+)', mermaid_src, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
        else:
            title = "System Diagram"
    d["title"] = title

    # Format the created_at date
    import datetime
    created_at = d.get("created_at")
    if created_at:
        try:
            dt = datetime.datetime.fromtimestamp(created_at)
            d["created_at_fmt"] = dt.strftime("%m.%d.%Y")
        except Exception:
            d["created_at_fmt"] = ""
    else:
        d["created_at_fmt"] = ""

    return d
