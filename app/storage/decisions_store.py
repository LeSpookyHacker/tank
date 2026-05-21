"""CRUD for the decisions log.

A decision is any deliberate choice the engineer (or org) makes:
design choices, accepted risks, deferred fixes, security invariants.
Surface in chat and in nudges; warn when accepted-risks expire.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn

ALLOWED_KINDS = {
    "design_choice", "accepted_risk", "deferred_fix", "security_invariant",
}
ALLOWED_STATUS = {"open", "withdrawn", "expired", "reaffirmed"}


def create(*, title: str, body_md: str, body_md_redacted: str | None = None,
           kind: str = "design_choice",
           scope_entity_ids: list[str] | None = None,
           rationale: str | None = None,
           expires_at: float | None = None,
           owner_entity_id: str | None = None,
           source: str = "manual",
           source_doc_id: str | None = None) -> str:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unknown decision kind: {kind}")
    did = uuid.uuid4().hex
    now = time.time()
    body_red = body_md_redacted if body_md_redacted is not None else body_md
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO decisions "
            "(id, title, body_md, body_md_redacted, kind, status, "
            " scope_entity_ids, rationale, expires_at, owner_entity_id, "
            " source, source_doc_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)",
            (did, title, body_md, body_red, kind,
             json.dumps(scope_entity_ids or []),
             rationale, expires_at, owner_entity_id,
             source, source_doc_id, now, now),
        )
    return did


def get(decision_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM decisions WHERE id = ?", (decision_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_filtered(*, kind: str | None = None,
                  status: str | None = "open",
                  scope_entity_id: str | None = None,
                  limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM decisions WHERE 1=1"
    params: list = []
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if scope_entity_id:
        sql += " AND scope_entity_ids LIKE ?"
        params.append(f'%"{scope_entity_id}"%')
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(sql, params).fetchall()
    return [_hydrate(r) for r in rows]


def recent(days: int = 30, limit: int = 50) -> list[dict]:
    cutoff = time.time() - days * 86400
    rows = get_conn().execute(
        "SELECT * FROM decisions WHERE created_at >= ? "
        "ORDER BY created_at DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def expiring_soon(within_days: int = 7) -> list[dict]:
    """Decisions with `expires_at` between now and now+within_days."""
    now = time.time()
    cutoff = now + within_days * 86400
    rows = get_conn().execute(
        "SELECT * FROM decisions "
        "WHERE status = 'open' AND expires_at IS NOT NULL "
        "AND expires_at <= ? AND expires_at >= ? "
        "ORDER BY expires_at",
        (cutoff, now),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def set_status(decision_id: str, status: str) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"unknown status: {status}")
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE decisions SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), decision_id),
        )


def reaffirm(decision_id: str, extend_days: int = 90) -> None:
    """Convenience: set status='reaffirmed' and bump expires_at."""
    new_expiry = time.time() + extend_days * 86400
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE decisions SET status = 'reaffirmed', "
            "expires_at = ?, updated_at = ? WHERE id = ?",
            (new_expiry, time.time(), decision_id),
        )


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["scope_entity_ids"] = json.loads(d.get("scope_entity_ids") or "[]")
    except Exception:
        d["scope_entity_ids"] = []
    return d
