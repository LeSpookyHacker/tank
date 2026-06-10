"""CRUD for the risk register.

Each risk tracks inherent likelihood × impact, the controls in place,
residual likelihood × impact after controls, and the chosen treatment
(mitigate / accept / transfer / avoid). Differs from the decisions log:
the decisions log records a deliberate choice; the risk register tracks
ongoing exposure with scoring.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn

ALLOWED_CATEGORIES = {
    "data_breach", "availability", "supply_chain", "access_control",
    "regulatory", "ai_model_abuse", "insider_threat", "third_party",
    "infrastructure", "application", "other",
}
ALLOWED_TREATMENTS = {"mitigate", "accept", "transfer", "avoid"}
ALLOWED_STATUS = {"open", "closed", "transferred"}


def create(
    *,
    title: str,
    description: str,
    category: str,
    inherent_likelihood: int = 3,
    inherent_impact: int = 3,
    residual_likelihood: int | None = None,
    residual_impact: int | None = None,
    treatment: str = "mitigate",
    treatment_rationale: str | None = None,
    owner_entity_id: str | None = None,
    scope_entity_ids: list[str] | None = None,
    controls: list[str] | None = None,
    review_at: int | None = None,
    decision_id: str | None = None,
    project_id: str | None = None,
) -> str:
    if category not in ALLOWED_CATEGORIES:
        category = "other"
    if treatment not in ALLOWED_TREATMENTS:
        treatment = "mitigate"
    rid = uuid.uuid4().hex
    now = int(time.time())
    rl = residual_likelihood if residual_likelihood is not None else inherent_likelihood
    ri = residual_impact if residual_impact is not None else inherent_impact
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO risks "
            "(id, title, description, category, inherent_likelihood, inherent_impact, "
            " controls_json, residual_likelihood, residual_impact, treatment, "
            " treatment_rationale, owner_entity_id, status, review_at, "
            " scope_entity_ids, decision_id, project_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)",
            (rid, title, description, category,
             inherent_likelihood, inherent_impact,
             json.dumps(controls or []),
             rl, ri, treatment, treatment_rationale,
             owner_entity_id, review_at,
             json.dumps(scope_entity_ids or []),
             decision_id, project_id, now, now),
        )
    return rid


def get(risk_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM risks WHERE id = ?", (risk_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def list_all(
    *,
    status: str | None = "open",
    category: str | None = None,
    project_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = "SELECT * FROM risks WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if category:
        sql += " AND category = ?"
        params.append(category)
    if project_id:
        sql += " AND project_id = ?"
        params.append(project_id)
    sql += " ORDER BY (residual_likelihood * residual_impact) DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(sql, params).fetchall()
    return [_hydrate(r) for r in rows]


def review_overdue(as_of: int | None = None) -> list[dict]:
    now = as_of or int(time.time())
    rows = get_conn().execute(
        "SELECT * FROM risks WHERE status = 'open' AND review_at IS NOT NULL "
        "AND review_at <= ? ORDER BY review_at",
        (now,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def update_assessment(
    risk_id: str,
    *,
    residual_likelihood: int,
    residual_impact: int,
    treatment: str,
    treatment_rationale: str | None = None,
    controls: list[str] | None = None,
    review_at: int | None = None,
) -> None:
    now = int(time.time())
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE risks SET residual_likelihood=?, residual_impact=?, "
            "treatment=?, treatment_rationale=?, controls_json=?, "
            "review_at=?, updated_at=? WHERE id=?",
            (residual_likelihood, residual_impact, treatment,
             treatment_rationale,
             json.dumps(controls) if controls is not None else None,
             review_at, now, risk_id),
        )


def set_status(risk_id: str, status: str, closure_rationale: str | None = None) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"unknown status: {status}")
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE risks SET status=?, closure_rationale=?, updated_at=? WHERE id=?",
            (status, closure_rationale, int(time.time()), risk_id),
        )


def counts_by_status() -> dict:
    rows = get_conn().execute(
        "SELECT status, COUNT(*) AS n FROM risks GROUP BY status"
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def _hydrate(row) -> dict:
    d = dict(row)
    for f in ("controls_json", "scope_entity_ids"):
        try:
            d[f.replace("_json", "")] = json.loads(d.pop(f, "[]") or "[]")
        except Exception:
            d[f.replace("_json", "")] = []
    d["inherent_score"] = d.get("inherent_likelihood", 3) * d.get("inherent_impact", 3)
    d["residual_score"] = d.get("residual_likelihood", 3) * d.get("residual_impact", 3)
    return d
