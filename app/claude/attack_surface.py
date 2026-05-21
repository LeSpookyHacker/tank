"""Attack-surface ledger.

A weekly snapshot of all Endpoint entities + their attrs. The scheduler
runs `snapshot()` Sunday 09:00; the UI shows diff vs prior.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn
from app.storage import entities_store


def snapshot() -> str:
    """Capture current Endpoint state. Returns snapshot id."""
    endpoints = entities_store.list_entities(type_="Endpoint", limit=500)
    payload = [
        {"id": e["id"], "name": e["name"],
         "description": e.get("description"),
         "attrs": json.loads(e.get("attrs_json") or "{}"),
         "updated_at": e.get("updated_at")}
        for e in endpoints
    ]
    summary = _diff_summary(payload)
    sid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO attack_surface_snapshots "
            "(id, snapshot_at, endpoints_json, summary_md) "
            "VALUES (?, ?, ?, ?)",
            (sid, time.time(), json.dumps(payload), summary),
        )
    return sid


def latest() -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM attack_surface_snapshots "
        "ORDER BY snapshot_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return _hydrate(row)


def history(limit: int = 12) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM attack_surface_snapshots "
        "ORDER BY snapshot_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def _diff_summary(new_payload: list[dict]) -> str:
    """Compare against previous snapshot, return a short markdown summary."""
    prev = latest()
    if not prev:
        return f"Initial snapshot. {len(new_payload)} endpoints captured."
    old_ids = {e["id"] for e in prev["endpoints"]}
    new_ids = {e["id"] for e in new_payload}
    added = new_ids - old_ids
    removed = old_ids - new_ids
    lines = [f"Endpoints: {len(new_payload)} (was {len(prev['endpoints'])})"]
    if added:
        lines.append(f"+ {len(added)} new")
    if removed:
        lines.append(f"- {len(removed)} removed")
    return " · ".join(lines)


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["endpoints"] = json.loads(d.get("endpoints_json") or "[]")
    except Exception:
        d["endpoints"] = []
    return d
