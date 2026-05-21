"""CRUD for the `documents` table."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.db import LOCK, get_conn


def insert_document(*, source_path: str, kind: str, title: str | None,
                    sha256: str, size_bytes: int, category: str,
                    meta: dict | None = None) -> str:
    doc_id = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO documents "
            "(id, kind, source_path, title, sha256, size_bytes, category, "
            " meta_json, ingested_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (doc_id, kind, source_path, title, sha256, size_bytes,
             category, json.dumps(meta or {}), time.time()),
        )
    return doc_id


def get_document(doc_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,),
    ).fetchone()
    return dict(row) if row else None


def find_by_sha256(sha: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM documents WHERE sha256 = ?", (sha,),
    ).fetchone()
    return dict(row) if row else None


def list_documents(*, category: str | None = None,
                   limit: int = 200) -> list[dict]:
    if category:
        rows = get_conn().execute(
            "SELECT * FROM documents WHERE category = ? "
            "ORDER BY ingested_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM documents ORDER BY ingested_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_status(doc_id: str, status: str,
                  error_message: str | None = None) -> None:
    conn = get_conn()
    with LOCK:
        if error_message:
            # Merge error into meta_json without clobbering.
            row = conn.execute(
                "SELECT meta_json FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            meta = json.loads(row["meta_json"] or "{}") if row else {}
            meta["error"] = error_message
            conn.execute(
                "UPDATE documents SET status = ?, meta_json = ? WHERE id = ?",
                (status, json.dumps(meta), doc_id),
            )
        else:
            conn.execute(
                "UPDATE documents SET status = ? WHERE id = ?",
                (status, doc_id),
            )


def count_by_category() -> dict[str, int]:
    rows = get_conn().execute(
        "SELECT category, COUNT(*) AS n FROM documents GROUP BY category"
    ).fetchall()
    return {r["category"]: r["n"] for r in rows}
