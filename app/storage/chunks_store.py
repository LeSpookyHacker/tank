"""CRUD for `chunks`, `chunks_fts`, and `chunks_vec`.

Writes both the keyword (FTS5) and vector (sqlite-vec) indexes so the
KB search layer can run hybrid retrieval. Falls back to FTS-only if
sqlite-vec didn't load.
"""
from __future__ import annotations

import json
import sqlite3
import struct
import uuid

from app.db import LOCK, get_conn


def _pack_embedding(vec: list[float]) -> bytes:
    """sqlite-vec accepts FLOAT32 packed as little-endian bytes."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _has_vec_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','virtual') "
        "AND name = 'chunks_vec'"
    ).fetchone()
    return row is not None


def bulk_insert_chunks(*, document_id: str,
                       chunks: list[dict]) -> list[str]:
    """Insert chunk rows + FTS5 entries.

    Each chunk dict needs: ordinal, text_original, text_redacted,
    token_count, section_path, meta.

    Vector embeddings come separately via `write_vec()` because the
    embedder is async-friendly.
    """
    conn = get_conn()
    ids: list[str] = []
    with LOCK:
        for c in chunks:
            cid = uuid.uuid4().hex
            ids.append(cid)
            conn.execute(
                "INSERT INTO chunks "
                "(id, document_id, ordinal, text_redacted, text_original, "
                " token_count, section_path, meta_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, document_id, c["ordinal"], c["text_redacted"],
                 c["text_original"], c["token_count"],
                 c.get("section_path"), json.dumps(c.get("meta", {}))),
            )
            conn.execute(
                "INSERT INTO chunks_fts (chunk_id, text_redacted, section_path) "
                "VALUES (?, ?, ?)",
                (cid, c["text_redacted"], c.get("section_path", "")),
            )
    return ids


def write_vec(chunk_ids: list[str], embeddings: list[list[float]]) -> int:
    """Write embeddings to chunks_vec. Returns count of rows written.

    Silently no-ops if sqlite-vec isn't available (caller still has
    FTS5 for keyword retrieval).
    """
    if len(chunk_ids) != len(embeddings):
        raise ValueError("chunk_ids and embeddings length mismatch")
    conn = get_conn()
    if not _has_vec_table(conn):
        return 0
    written = 0
    with LOCK:
        for cid, vec in zip(chunk_ids, embeddings):
            conn.execute(
                "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) "
                "VALUES (?, ?)",
                (cid, _pack_embedding(vec)),
            )
            written += 1
    return written


def list_chunks_for_doc(document_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal",
        (document_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_chunk(chunk_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    return dict(row) if row else None


def chunks_for_ids(chunk_ids: list[str]) -> list[dict]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" * len(chunk_ids))
    rows = get_conn().execute(
        f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids,
    ).fetchall()
    return [dict(r) for r in rows]
