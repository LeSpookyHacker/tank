"""Compliance evidence queries."""
from __future__ import annotations

from app.db import get_conn


def find_evidence(control_id: str) -> dict:
    """Return the evidence rows mapped to a control_id."""
    rows = get_conn().execute(
        "SELECT * FROM compliance_evidence WHERE control_id = ?",
        (control_id,),
    ).fetchall()
    return {"control_id": control_id,
            "evidence": [dict(r) for r in rows]}


def controls_with_no_evidence() -> list[str]:
    """All Control entities lacking any compliance_evidence row."""
    rows = get_conn().execute(
        "SELECT e.id, e.name FROM entities e "
        "WHERE e.type = 'Control' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM compliance_evidence ce "
        "  WHERE ce.control_id = e.id"
        ")"
    ).fetchall()
    return [r["id"] for r in rows]


def find_evidence_with_titles(control_id: str) -> list[dict]:
    """Return evidence rows for a control, enriched with document titles."""
    rows = get_conn().execute(
        "SELECT ce.evidence_kind, ce.evidence_id, ce.confidence, "
        "       ce.captured_at, d.title, d.category, d.source_path "
        "FROM compliance_evidence ce "
        "LEFT JOIN documents d ON ce.evidence_id = d.id "
        "WHERE ce.control_id = ? "
        "ORDER BY ce.confidence DESC",
        (control_id,),
    ).fetchall()
    return [dict(r) for r in rows]
