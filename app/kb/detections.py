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
    # Escape LIKE special chars so user-supplied IDs are matched literally.
    attack_id_like = (
        attack_id_up.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    # Detections that mention the technique id in attrs or name.
    rows = get_conn().execute(
        "SELECT id, name, description, attrs_json "
        "FROM entities WHERE type = 'Detection' "
        "AND (attrs_json LIKE ? ESCAPE '\\' "
        "OR description LIKE ? ESCAPE '\\' "
        "OR name LIKE ? ESCAPE '\\')",
        (f"%{attack_id_like}%", f"%{attack_id_like}%", f"%{attack_id_like}%"),
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


def coverage_by_technique() -> dict:
    """Return per-technique coverage summary for the coverage map page.

    Makes one query per technique (not N*M) and returns a dict with:
      - techniques: list of {id, name, description, detections, covered}
        sorted covered-first then alphabetically
      - covered_count: int
      - gap_count: int
      - total: int
      - coverage_pct: float 0-100
    """
    techniques = entities_store.list_entities(type_="AttackTechnique",
                                              limit=200)
    rows = []
    for t in techniques:
        result = find_for_technique(t["name"])
        rows.append({
            "id": t["id"],
            "name": t["name"],
            "description": t.get("description") or "",
            "detections": result["detections"],
            "covered": len(result["detections"]) > 0,
        })

    # covered first, then gaps; within each group sort by name
    rows.sort(key=lambda r: (0 if r["covered"] else 1, r["name"].lower()))

    covered = sum(1 for r in rows if r["covered"])
    total = len(rows)
    return {
        "techniques": rows,
        "covered_count": covered,
        "gap_count": total - covered,
        "total": total,
        "coverage_pct": round(covered / total * 100) if total else 0,
    }
