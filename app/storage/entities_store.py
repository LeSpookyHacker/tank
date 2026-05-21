"""CRUD for `entities` and `entity_chunks`.

Dedup is by `(type, name_normalized)`. Re-extracting the same entity
bumps `updated_at` rather than creating a duplicate.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def _normalize(name: str) -> str:
    return name.strip().lower()


def upsert_entity(*, type_: str, name: str, description: str | None = None,
                  attrs: dict | None = None, confidence: float = 1.0,
                  provenance: str = "inferred",
                  first_seen_doc: str | None = None) -> str:
    norm = _normalize(name)
    conn = get_conn()
    now = time.time()
    with LOCK:
        existing = conn.execute(
            "SELECT id, attrs_json, confidence FROM entities "
            "WHERE type = ? AND name_normalized = ?",
            (type_, norm),
        ).fetchone()
        if existing:
            # Merge attrs, keep max confidence.
            old_attrs = json.loads(existing["attrs_json"] or "{}")
            old_attrs.update(attrs or {})
            new_conf = max(existing["confidence"], confidence)
            conn.execute(
                "UPDATE entities "
                "SET description = COALESCE(?, description), "
                "    attrs_json = ?, confidence = ?, updated_at = ? "
                "WHERE id = ?",
                (description, json.dumps(old_attrs), new_conf,
                 now, existing["id"]),
            )
            return existing["id"]

        eid = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO entities "
            "(id, type, name, name_normalized, description, attrs_json, "
            " confidence, provenance, first_seen_doc, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, type_, name, norm, description, json.dumps(attrs or {}),
             confidence, provenance, first_seen_doc, now, now),
        )
        return eid


def link_chunk(entity_id: str, chunk_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT OR IGNORE INTO entity_chunks (entity_id, chunk_id) "
            "VALUES (?, ?)",
            (entity_id, chunk_id),
        )


def get_entity(entity_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    return dict(row) if row else None


def find_entity(type_: str, name: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM entities WHERE type = ? AND name_normalized = ?",
        (type_, _normalize(name)),
    ).fetchone()
    return dict(row) if row else None


def list_entities(*, type_: str | None = None, limit: int = 200,
                  offset: int = 0) -> list[dict]:
    if type_:
        rows = get_conn().execute(
            "SELECT * FROM entities WHERE type = ? "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (type_, limit, offset),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM entities ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def linked_chunks(entity_id: str, limit: int = 5) -> list[str]:
    rows = get_conn().execute(
        "SELECT chunk_id FROM entity_chunks WHERE entity_id = ? LIMIT ?",
        (entity_id, limit),
    ).fetchall()
    return [r["chunk_id"] for r in rows]


def count_by_type() -> dict[str, int]:
    rows = get_conn().execute(
        "SELECT type, COUNT(*) AS n FROM entities GROUP BY type"
    ).fetchall()
    return {r["type"]: r["n"] for r in rows}


def set_provenance(entity_id: str, provenance: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE entities SET provenance = ?, updated_at = ? WHERE id = ?",
            (provenance, time.time(), entity_id),
        )
