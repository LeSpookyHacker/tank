"""CRUD for versioned threat models.

A threat_model row is the frozen STRIDE artifact for a service at a
given point in time. The `arch_snapshot_hash` is sha256 over the
service's contributing chunks at gen time — drift detection compares
that to the current hash to decide if a regenerate is overdue.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def insert(*, service_entity_id: str, title: str,
           body_md: str, body_md_redacted: str,
           threats: list[dict],
           arch_snapshot_hash: str,
           confirmed_by_user: bool = False) -> str:
    """Insert a new TM at version = max(prior)+1 for this service."""
    tmid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        prior = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM threat_models "
            "WHERE service_entity_id = ?",
            (service_entity_id,),
        ).fetchone()
        next_version = (prior["v"] if prior else 0) + 1
        conn.execute(
            "INSERT INTO threat_models "
            "(id, service_entity_id, version, title, body_md, "
            " body_md_redacted, threats_json, arch_snapshot_hash, "
            " generated_at, confirmed_by_user) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tmid, service_entity_id, next_version, title,
             body_md, body_md_redacted, json.dumps(threats),
             arch_snapshot_hash, now, 1 if confirmed_by_user else 0),
        )
    return tmid


def latest_for_service(service_entity_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM threat_models WHERE service_entity_id = ? "
        "ORDER BY version DESC LIMIT 1",
        (service_entity_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_versions(service_entity_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM threat_models WHERE service_entity_id = ? "
        "ORDER BY version DESC",
        (service_entity_id,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def get(tm_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM threat_models WHERE id = ?", (tm_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_all_latest() -> list[dict]:
    """Latest TM per service. Used by drift detection + ownership board."""
    rows = get_conn().execute(
        "SELECT t.* FROM threat_models t "
        "JOIN ("
        "  SELECT service_entity_id, MAX(version) AS v "
        "  FROM threat_models GROUP BY service_entity_id"
        ") m ON m.service_entity_id = t.service_entity_id "
        "AND m.v = t.version"
    ).fetchall()
    return [_hydrate(r) for r in rows]


def confirm(tm_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE threat_models SET confirmed_by_user = 1 WHERE id = ?",
            (tm_id,),
        )


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["threats"] = json.loads(d.get("threats_json") or "[]")
    except Exception:
        d["threats"] = []
    return d
