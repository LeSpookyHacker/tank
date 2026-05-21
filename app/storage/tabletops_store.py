"""CRUD for tabletop exercises."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def create(*, scenario_md: str,
           scope_service_id: str | None = None,
           threat_kind: str | None = None,
           injects: list[dict] | None = None,
           participants: str | None = None) -> str:
    tid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO tabletops "
            "(id, scenario_md, scope_service_id, threat_kind, "
            " injects_json, participants, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, scenario_md, scope_service_id, threat_kind,
             json.dumps(injects or []), participants, now),
        )
    return tid


def get(tt_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM tabletops WHERE id = ?", (tt_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_all(limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM tabletops ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def mark_ran(tt_id: str, lessons_md: str | None = None) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE tabletops SET ran_at = ?, lessons_md = ? WHERE id = ?",
            (time.time(), lessons_md, tt_id),
        )


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["injects"] = json.loads(d.get("injects_json") or "[]")
    except Exception:
        d["injects"] = []
    return d
