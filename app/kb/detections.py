"""Detection-coverage queries.

Reads Detection entities (created by the Sigma parser + entity
extractor) and their links to AttackTechnique entities. Surfaces:
- which techniques are covered (any Detection exists),
- which services are exposed to which techniques (from threat models),
- gaps where exposure exists but no Detection covers it.
"""
from __future__ import annotations

from app.db import get_conn
from app.storage import entities_store, relationships_store


def find_for_technique(attack_id: str) -> dict:
    """Detection entities tagged with the given ATT&CK technique."""
    attack_id_up = attack_id.strip().upper()
    # Detections that mention the technique id in attrs or name.
    rows = get_conn().execute(
        "SELECT id, name, description, attrs_json "
        "FROM entities WHERE type = 'Detection' "
        "AND (attrs_json LIKE ? OR description LIKE ? OR name LIKE ?)",
        (f"%{attack_id_up}%", f"%{attack_id_up}%", f"%{attack_id_up}%"),
    ).fetchall()
    return {
        "attack_id": attack_id_up,
        "detections": [
            {"id": r["id"], "name": r["name"],
             "description": r["description"]}
            for r in rows
        ],
    }


def coverage_table(limit_services: int = 30) -> list[dict]:
    """Return services × techniques covered/uncovered."""
    techniques = entities_store.list_entities(type_="AttackTechnique",
                                              limit=200)
    services = entities_store.list_entities(type_="Service",
                                            limit=limit_services)
    out = []
    for s in services:
        for t in techniques:
            row = find_for_technique(t["name"])
            out.append({
                "service_id": s["id"], "service_name": s["name"],
                "technique_id": t["name"],
                "covered_by": [d["name"] for d in row["detections"]],
            })
    return out
