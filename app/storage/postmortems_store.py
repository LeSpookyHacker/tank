"""CRUD for postmortem drafts."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn

ALLOWED_STATUS = {"draft", "published", "withdrawn"}


def create(*, title: str, fields: dict,
           body_md: str | None = None,
           body_md_redacted: str | None = None,
           incident_date: float | None = None,
           severity: str | None = None,
           services_affected: list[str] | None = None) -> str:
    pmid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO postmortems_drafts "
            "(id, title, incident_date, severity, status, fields_json, "
            " body_md, body_md_redacted, services_affected, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)",
            (pmid, title, incident_date, severity,
             json.dumps(fields),
             body_md, body_md_redacted,
             json.dumps(services_affected or []),
             now, now),
        )
    return pmid


def get(pm_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM postmortems_drafts WHERE id = ?", (pm_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_by_status(status: str | None = None, limit: int = 50) -> list[dict]:
    if status:
        rows = get_conn().execute(
            "SELECT * FROM postmortems_drafts WHERE status = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM postmortems_drafts "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_hydrate(r) for r in rows]


def update_fields(pm_id: str, fields: dict,
                  body_md: str | None = None,
                  body_md_redacted: str | None = None) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE postmortems_drafts SET fields_json = ?, body_md = ?, "
            "body_md_redacted = ?, updated_at = ? WHERE id = ?",
            (json.dumps(fields), body_md, body_md_redacted,
             time.time(), pm_id),
        )


def set_status(pm_id: str, status: str) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"unknown status: {status}")
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE postmortems_drafts SET status = ?, updated_at = ? "
            "WHERE id = ?",
            (status, time.time(), pm_id),
        )


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["fields"] = json.loads(d.get("fields_json") or "{}")
    except Exception:
        d["fields"] = {}
    try:
        d["services_affected"] = json.loads(d.get("services_affected") or "[]")
    except Exception:
        d["services_affected"] = []
    return d
