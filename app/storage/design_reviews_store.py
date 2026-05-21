"""CRUD for design reviews.

A design review row tracks an intake → checklist → approval/rejection
flow. The `decisions_json` field accumulates IDs of `decisions` rows
created as the review progresses.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn

ALLOWED_STATUS = {"intake", "reviewing", "approved", "rejected", "withdrawn"}


def create(*, title: str, body_md: str, body_md_redacted: str | None = None,
           requester: str | None = None,
           scope_entity_ids: list[str] | None = None,
           checklist: list[dict] | None = None) -> str:
    drid = uuid.uuid4().hex
    now = time.time()
    body_red = body_md_redacted if body_md_redacted is not None else body_md
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO design_reviews "
            "(id, title, status, requester, scope_entity_ids, body_md, "
            " body_md_redacted, checklist_json, decisions_json, "
            " created_at, updated_at) "
            "VALUES (?, ?, 'intake', ?, ?, ?, ?, ?, '[]', ?, ?)",
            (drid, title, requester,
             json.dumps(scope_entity_ids or []),
             body_md, body_red,
             json.dumps(checklist or []),
             now, now),
        )
    return drid


def get(dr_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM design_reviews WHERE id = ?", (dr_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_by_status(status: str = "intake", limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM design_reviews WHERE status = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (status, limit),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def list_all(limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM design_reviews ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def update_checklist(dr_id: str, checklist: list[dict]) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE design_reviews SET checklist_json = ?, updated_at = ? "
            "WHERE id = ?",
            (json.dumps(checklist), time.time(), dr_id),
        )


def update_body(dr_id: str, body_md: str, body_md_redacted: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE design_reviews SET body_md = ?, body_md_redacted = ?, "
            "updated_at = ? WHERE id = ?",
            (body_md, body_md_redacted, time.time(), dr_id),
        )


def set_status(dr_id: str, status: str) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"unknown status: {status}")
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE design_reviews SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), dr_id),
        )


def add_decision(dr_id: str, decision_id: str) -> None:
    row = get(dr_id)
    if not row:
        return
    ids = row.get("decisions") or []
    if decision_id not in ids:
        ids.append(decision_id)
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE design_reviews SET decisions_json = ?, updated_at = ? "
            "WHERE id = ?",
            (json.dumps(ids), time.time(), dr_id),
        )


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["checklist"] = json.loads(d.get("checklist_json") or "[]")
    except Exception:
        d["checklist"] = []
    try:
        d["scope_entity_ids"] = json.loads(d.get("scope_entity_ids") or "[]")
    except Exception:
        d["scope_entity_ids"] = []
    try:
        d["decisions"] = json.loads(d.get("decisions_json") or "[]")
    except Exception:
        d["decisions"] = []
    return d
