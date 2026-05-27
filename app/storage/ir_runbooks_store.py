"""CRUD for incident-response runbooks."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def create(
    *,
    threat_scenario: str,
    runbook_md: str,
    runbook_md_redacted: str,
    service_entity_id: str | None = None,
    severity_trigger: str = "any",
    contacts: list[dict] | None = None,
    escalation: list[dict] | None = None,
    tabletop_id: str | None = None,
    project_id: str | None = None,
) -> str:
    rid = uuid.uuid4().hex
    now = int(time.time())
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO ir_runbooks "
            "(id, service_entity_id, threat_scenario, severity_trigger, "
            " runbook_md, runbook_md_redacted, contacts_json, escalation_json, "
            " version, generated_at, tabletop_id, project_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (rid, service_entity_id, threat_scenario, severity_trigger,
             runbook_md, runbook_md_redacted,
             json.dumps(contacts or []),
             json.dumps(escalation or []),
             now, tabletop_id, project_id),
        )
    return rid


def get(runbook_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM ir_runbooks WHERE id = ?", (runbook_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_all(
    *,
    service_entity_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    if service_entity_id:
        rows = get_conn().execute(
            "SELECT * FROM ir_runbooks WHERE service_entity_id = ? "
            "ORDER BY generated_at DESC LIMIT ?",
            (service_entity_id, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM ir_runbooks ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_hydrate(r) for r in rows]


def services_with_runbook() -> set[str]:
    """Return service_entity_ids that have at least one runbook."""
    rows = get_conn().execute(
        "SELECT DISTINCT service_entity_id FROM ir_runbooks "
        "WHERE service_entity_id IS NOT NULL"
    ).fetchall()
    return {r[0] for r in rows}


def confirm(runbook_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE ir_runbooks SET confirmed_by_user = 1 WHERE id = ?",
            (runbook_id,),
        )


def delete(runbook_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute("DELETE FROM ir_runbooks WHERE id = ?", (runbook_id,))


def _hydrate(row) -> dict:
    d = dict(row)
    for f in ("contacts_json", "escalation_json"):
        key = f.replace("_json", "")
        try:
            d[key] = json.loads(d.pop(f, "[]") or "[]")
        except Exception:
            d[key] = []
    return d
