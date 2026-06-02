"""CRUD for `service_ownership` — operational ownership + on-call roster.

Distinct from `owned_store` (the user's personal RACI claims). This is the
org-wide answer to "who operates this service, who's on-call, who do I
escalate to?" — surfaced on the entity page, in IR runbooks, on the Today
home, and via the `get_service_ownership` chat tool.

Single global SQLite connection; all writes under `LOCK`.
"""
from __future__ import annotations

import json
import time

from app.db import LOCK, get_conn


def set_owner(*, entity_id: str,
              primary_owner_entity_id: str | None = None,
              secondary_owner_entity_id: str | None = None,
              on_call_contact: str | None = None,
              escalation: list[dict] | None = None,
              slack_channel: str | None = None,
              pager_handle: str | None = None,
              provenance: str = "user") -> None:
    """Insert or replace the ownership row for a Service entity."""
    conn = get_conn()
    now = time.time()
    with LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO service_ownership "
            "(entity_id, primary_owner_entity_id, secondary_owner_entity_id, "
            " on_call_contact, escalation_json, slack_channel, pager_handle, "
            " provenance, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_id, primary_owner_entity_id, secondary_owner_entity_id,
             on_call_contact, json.dumps(escalation or []),
             slack_channel, pager_handle, provenance, now),
        )


def get(entity_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM service_ownership WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["escalation"] = json.loads(out.get("escalation_json") or "[]")
    except (ValueError, TypeError):
        out["escalation"] = []
    return out


def list_all() -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM service_ownership ORDER BY updated_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["escalation"] = json.loads(d.get("escalation_json") or "[]")
        except (ValueError, TypeError):
            d["escalation"] = []
        out.append(d)
    return out


def clear(entity_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "DELETE FROM service_ownership WHERE entity_id = ?",
            (entity_id,),
        )


def seed_from_graph(entity_id: str) -> dict | None:
    """Best-effort: propose a primary owner from existing Person→Service
    edges (manages/owns/operates). Only writes an `inferred` row when no
    row exists yet — never clobbers a user-entered one.
    """
    if get(entity_id) is not None:
        return get(entity_id)
    row = get_conn().execute(
        "SELECT src_id FROM relationships "
        "WHERE dst_id = ? AND kind IN ('manages', 'owns', 'operates') "
        "ORDER BY confidence DESC LIMIT 1",
        (entity_id,),
    ).fetchone()
    if not row:
        return None
    set_owner(entity_id=entity_id,
              primary_owner_entity_id=row["src_id"],
              provenance="inferred")
    return get(entity_id)
