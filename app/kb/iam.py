"""IAM-policy risk queries."""
from __future__ import annotations

import json

from app.db import get_conn


def find_risks(limit: int = 10) -> dict:
    """Return top-N IAMPolicy entities ranked by attrs.risk_score."""
    rows = get_conn().execute(
        "SELECT id, name, description, attrs_json "
        "FROM entities WHERE type = 'IAMPolicy'"
    ).fetchall()
    scored = []
    for r in rows:
        try:
            attrs = json.loads(r["attrs_json"] or "{}")
        except Exception:
            attrs = {}
        scored.append({
            "id": r["id"], "name": r["name"],
            "description": r["description"],
            "risk_score": float(attrs.get("risk_score") or 0.0),
            "risk_callouts": attrs.get("risk_callouts") or [],
        })
    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"policies": scored[:limit]}
