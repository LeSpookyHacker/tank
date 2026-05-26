# organizations_store.py — CRUD for the organizations table (single-org model).
from __future__ import annotations

from app.db import LOCK, get_conn


def get_org() -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM organizations ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def update_org(name: str | None = None,
               description: str | None = None,
               industry: str | None = None) -> None:
    updates: dict = {}
    if name is not None:
        updates["name"] = name.strip()
    if description is not None:
        updates["description"] = description.strip()
    if industry is not None:
        updates["industry"] = industry.strip()
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())
    conn = get_conn()
    with LOCK:
        conn.execute(
            f"UPDATE organizations SET {set_clause} "
            "WHERE id = (SELECT id FROM organizations ORDER BY created_at ASC LIMIT 1)",
            values,
        )
