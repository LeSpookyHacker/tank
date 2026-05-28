"""CRUD for policy_artifact — living security policy documents.

Mirrors threat_models_store.py pattern: versioned rows, dual content
(redacted + rehydrated), status lifecycle.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn

POLICY_KINDS = [
    "acceptable_use",
    "incident_response",
    "secure_sdl",
    "vulnerability_management",
    "data_classification",
]

POLICY_DISPLAY_NAMES = {
    "acceptable_use": "Acceptable Use Policy",
    "incident_response": "Incident Response Policy",
    "secure_sdl": "Secure Development Lifecycle (SDL) Policy",
    "vulnerability_management": "Vulnerability Management Policy",
    "data_classification": "Data Classification Policy",
}

_ALLOWED_STATUSES = {"draft", "reviewed", "approved"}


def create(
    *,
    kind: str,
    content_md: str,
    content_md_redacted: str,
    project_id: str | None = None,
) -> str:
    pid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        existing = get_latest(kind)
        version = (existing["version"] + 1) if existing else 1
        conn.execute(
            "INSERT INTO policy_artifact "
            "(id, kind, created_at, updated_at, content_md, content_md_redacted, "
            " status, linked_decision_ids, version, project_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, kind, now, now, content_md, content_md_redacted,
             "draft", "[]", version, project_id),
        )
    return pid


def get_latest(kind: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM policy_artifact WHERE kind = ? "
        "ORDER BY version DESC LIMIT 1",
        (kind,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["linked_decision_ids"] = json.loads(d.get("linked_decision_ids") or "[]")
    except Exception:
        d["linked_decision_ids"] = []
    return d


def get_by_id(policy_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM policy_artifact WHERE id = ?", (policy_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["linked_decision_ids"] = json.loads(d.get("linked_decision_ids") or "[]")
    except Exception:
        d["linked_decision_ids"] = []
    return d


def list_all() -> list[dict]:
    """Return the latest version of each policy kind."""
    result = []
    for kind in POLICY_KINDS:
        p = get_latest(kind)
        result.append(p or {
            "id": None,
            "kind": kind,
            "status": None,
            "version": 0,
            "updated_at": None,
        })
    return result


def update(policy_id: str, *, content_md: str,
           content_md_redacted: str | None = None,
           status: str | None = None) -> None:
    if status and status not in _ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    conn = get_conn()
    now = time.time()
    with LOCK:
        fields = ["content_md = ?", "updated_at = ?"]
        values: list = [content_md, now]
        if content_md_redacted is not None:
            fields.append("content_md_redacted = ?")
            values.append(content_md_redacted)
        if status:
            fields.append("status = ?")
            values.append(status)
        values.append(policy_id)
        conn.execute(
            f"UPDATE policy_artifact SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def link_decision(policy_id: str, decision_id: str) -> None:
    row = get_by_id(policy_id)
    if not row:
        return
    ids = row["linked_decision_ids"]
    if decision_id not in ids:
        ids.append(decision_id)
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE policy_artifact SET linked_decision_ids = ? WHERE id = ?",
            (json.dumps(ids), policy_id),
        )
