"""CRUD for asset_inventory — the security stack audit template."""
from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn

# 15 canonical capability categories
CAPABILITY_CATEGORIES = [
    "Identity Provider (SSO/LDAP)",
    "Multi-Factor Authentication",
    "Secrets Management",
    "SIEM / Log Aggregation",
    "Web Application Firewall (WAF)",
    "Endpoint Detection & Response (EDR)",
    "Vulnerability Scanner",
    "Data Loss Prevention (DLP)",
    "Network Segmentation",
    "Backup & Recovery",
    "Patch Management",
    "Security Training Platform",
    "Bug Bounty / Penetration Testing",
    "Container / Supply Chain Security",
    "Cloud Security Posture Management (CSPM)",
]

_ALLOWED_STATUSES = {"none", "partial", "full"}


def upsert(
    *,
    capability_category: str,
    tool_name: str | None = None,
    deployment_status: str = "none",
    coverage_notes: str | None = None,
    known_gaps: str | None = None,
    project_id: str | None = None,
) -> str:
    if deployment_status not in _ALLOWED_STATUSES:
        deployment_status = "none"
    now = time.time()
    conn = get_conn()
    with LOCK:
        existing = conn.execute(
            "SELECT id FROM asset_inventory WHERE capability_category = ?",
            (capability_category,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE asset_inventory SET tool_name=?, deployment_status=?, "
                "coverage_notes=?, known_gaps=?, updated_at=? WHERE id=?",
                (tool_name, deployment_status, coverage_notes, known_gaps, now,
                 existing["id"]),
            )
            return existing["id"]
        iid = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO asset_inventory "
            "(id, created_at, updated_at, capability_category, tool_name, "
            " deployment_status, coverage_notes, known_gaps, project_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (iid, now, now, capability_category, tool_name,
             deployment_status, coverage_notes, known_gaps, project_id),
        )
        return iid


def get_all() -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM asset_inventory ORDER BY rowid"
    ).fetchall()
    existing = {dict(r)["capability_category"]: dict(r) for r in rows}
    # Return all 15 categories, filling in blanks for those not yet assessed.
    result = []
    for cat in CAPABILITY_CATEGORIES:
        if cat in existing:
            result.append(existing[cat])
        else:
            result.append({
                "id": None,
                "capability_category": cat,
                "tool_name": None,
                "deployment_status": "none",
                "coverage_notes": None,
                "known_gaps": None,
                "updated_at": None,
            })
    return result


def completion_percentage() -> int:
    """Percentage of categories that have been assessed (not 'none' status)."""
    rows = get_conn().execute(
        "SELECT COUNT(*) AS n FROM asset_inventory "
        "WHERE deployment_status != 'none'"
    ).fetchone()
    assessed = rows["n"] if rows else 0
    return round((assessed / len(CAPABILITY_CATEGORIES)) * 100)
