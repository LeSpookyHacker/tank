"""Minimal CRUD for the vulnerabilities intake table.

This table is the landing zone for findings from any source:
NVD CVE feed, GitHub Dependabot, scanners, or (via POST /api/vulnerabilities/intake)
the Nyx disclosure-triage tool.

Full triage UI / analysis is deferred. This store covers the schema
and the create/list/get primitives needed by the intake endpoint and
future reporting.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn

ALLOWED_SEVERITY = {"critical", "high", "medium", "low", "informational"}
ALLOWED_STATUS = {
    "open", "triaged", "in_remediation", "patched", "accepted", "wont_fix",
}
ALLOWED_SOURCES = {
    "nvd", "github_dependabot", "scanner", "manual", "disclosure",
}


def create(
    *,
    title: str,
    description: str | None = None,
    cve_id: str | None = None,
    cvss_score: float | None = None,
    cvss_vector: str | None = None,
    severity: str = "medium",
    source: str = "manual",
    affected_service_ids: list[str] | None = None,
    owner_entity_id: str | None = None,
    due_at: int | None = None,
    external_ref: str | None = None,
    project_id: str | None = None,
) -> str:
    if severity not in ALLOWED_SEVERITY:
        severity = "medium"
    if source not in ALLOWED_SOURCES:
        source = "manual"
    vid = uuid.uuid4().hex
    now = int(time.time())
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO vulnerabilities "
            "(id, cve_id, title, description, cvss_score, cvss_vector, severity, "
            " status, source, affected_service_ids, owner_entity_id, due_at, "
            " external_ref, project_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, cve_id, title, description, cvss_score, cvss_vector, severity,
             source,
             json.dumps(affected_service_ids or []),
             owner_entity_id, due_at, external_ref, project_id, now, now),
        )
    return vid


def get(vuln_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM vulnerabilities WHERE id = ?", (vuln_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_open(
    *,
    severity: str | None = None,
    source: str | None = None,
    project_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = "SELECT * FROM vulnerabilities WHERE status = 'open'"
    params: list = []
    if severity:
        sql += " AND severity = ?"
        params.append(severity)
    if source:
        sql += " AND source = ?"
        params.append(source)
    if project_id:
        sql += " AND project_id = ?"
        params.append(project_id)
    sql += " ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END, created_at DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(sql, params).fetchall()
    return [_hydrate(r) for r in rows]


def counts_by_severity() -> dict:
    rows = get_conn().execute(
        "SELECT severity, COUNT(*) AS n FROM vulnerabilities "
        "WHERE status NOT IN ('patched', 'wont_fix') GROUP BY severity"
    ).fetchall()
    return {r["severity"]: r["n"] for r in rows}


def average_age_days() -> float:
    row = get_conn().execute(
        "SELECT AVG((strftime('%s','now') - created_at) / 86400.0) AS avg_age "
        "FROM vulnerabilities WHERE status = 'open'"
    ).fetchone()
    val = row["avg_age"] if row else None
    return round(float(val), 1) if val else 0.0


def triage(vuln_id: str, *, severity: str | None = None, notes: str | None = None) -> None:
    """Move to triaged state with optional severity reassessment."""
    conn = get_conn()
    now = int(time.time())
    with LOCK:
        if severity and severity in ALLOWED_SEVERITY:
            conn.execute(
                "UPDATE vulnerabilities SET status='triaged', triage_status='triaged', "
                "severity=?, updated_at=? WHERE id=?",
                (severity, now, vuln_id),
            )
        else:
            conn.execute(
                "UPDATE vulnerabilities SET status='triaged', triage_status='triaged', "
                "updated_at=? WHERE id=?",
                (now, vuln_id),
            )


def assign(vuln_id: str, *, assigned_to: str, due_at: int | None = None) -> None:
    """Assign to an owner with an optional due date."""
    conn = get_conn()
    now = int(time.time())
    with LOCK:
        conn.execute(
            "UPDATE vulnerabilities SET status='in_remediation', "
            "triage_status='assigned', assigned_to=?, due_at=?, updated_at=? "
            "WHERE id=?",
            (assigned_to, due_at, now, vuln_id),
        )


def close(
    vuln_id: str,
    *,
    reason: str = "patched",
    accepted_rationale: str | None = None,
) -> None:
    """Close a vulnerability with a reason."""
    if reason not in ALLOWED_STATUS:
        reason = "patched"
    conn = get_conn()
    now = int(time.time())
    with LOCK:
        conn.execute(
            "UPDATE vulnerabilities SET status=?, triage_status='closed', "
            "accepted_rationale=?, updated_at=? WHERE id=?",
            (reason, accepted_rationale, now, vuln_id),
        )


def promote_to_risk(vuln_id: str) -> str | None:
    """Create a risk register entry from this vulnerability. Returns risk_id."""
    from app.storage import risks_store
    vuln = get(vuln_id)
    if not vuln:
        return None
    risk_id = risks_store.create(
        title=vuln.get("title") or "Untitled vulnerability",
        description=vuln.get("description") or "",
        category="vulnerability",
        inherent_likelihood=3,
        inherent_impact=_sev_to_impact(vuln.get("severity")),
    )
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE vulnerabilities SET promoted_to_risk_id=? WHERE id=?",
            (risk_id, vuln_id),
        )
    return risk_id


def list_triage_queue(limit: int = 100) -> list[dict]:
    """Return vulnerabilities that need triage (status = open, triage_status = new)."""
    sql = (
        "SELECT * FROM vulnerabilities "
        "WHERE triage_status = 'new' OR (triage_status IS NULL AND status = 'open') "
        "ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 "
        "WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END, "
        "created_at DESC LIMIT ?"
    )
    rows = get_conn().execute(sql, (limit,)).fetchall()
    return [_hydrate(r) for r in rows]


def _sev_to_impact(severity: str | None) -> int:
    return {"critical": 5, "high": 4, "medium": 3, "low": 2}.get(severity or "", 3)


def set_status(vuln_id: str, status: str) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"unknown status: {status}")
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE vulnerabilities SET status=?, updated_at=? WHERE id=?",
            (status, int(time.time()), vuln_id),
        )


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["affected_service_ids"] = json.loads(d.get("affected_service_ids") or "[]")
    except Exception:
        d["affected_service_ids"] = []
    return d
