"""CRUD for `relationships`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def upsert_relationship(*, src_id: str, dst_id: str, kind: str,
                        attrs: dict | None = None, confidence: float = 1.0,
                        provenance: str = "inferred",
                        first_seen_doc: str | None = None) -> str:
    conn = get_conn()
    now = time.time()
    with LOCK:
        existing = conn.execute(
            "SELECT id FROM relationships "
            "WHERE src_id = ? AND dst_id = ? AND kind = ?",
            (src_id, dst_id, kind),
        ).fetchone()
        if existing:
            # Merge attrs, keep max confidence.
            conn.execute(
                "UPDATE relationships "
                "SET attrs_json = "
                "    json_patch(COALESCE(attrs_json, '{}'), ?), "
                "    confidence = MAX(confidence, ?) "
                "WHERE id = ?",
                (json.dumps(attrs or {}), confidence, existing["id"]),
            )
            return existing["id"]

        rid = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO relationships "
            "(id, src_id, dst_id, kind, attrs_json, confidence, "
            " provenance, first_seen_doc, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, src_id, dst_id, kind, json.dumps(attrs or {}),
             confidence, provenance, first_seen_doc, now),
        )
        return rid


def list_for_entity(entity_id: str, *,
                    direction: str = "both",
                    kind: str | None = None) -> list[dict]:
    """direction ∈ {out, in, both}."""
    conn = get_conn()
    out: list[dict] = []
    if direction in ("out", "both"):
        sql = "SELECT * FROM relationships WHERE src_id = ?"
        params: list = [entity_id]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        out += [dict(r) for r in conn.execute(sql, params).fetchall()]
    if direction in ("in", "both"):
        sql = "SELECT * FROM relationships WHERE dst_id = ?"
        params = [entity_id]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        out += [dict(r) for r in conn.execute(sql, params).fetchall()]
    return out


def count_by_kind() -> dict[str, int]:
    rows = get_conn().execute(
        "SELECT kind, COUNT(*) AS n FROM relationships GROUP BY kind"
    ).fetchall()
    return {r["kind"]: r["n"] for r in rows}
