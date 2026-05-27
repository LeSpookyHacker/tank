"""Hybrid retrieval: sqlite-vec ANN + FTS5 BM25 + reciprocal rank fusion.

Falls back to FTS5-only if sqlite-vec didn't load.
"""
from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass

from app.db import get_conn


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    document_id: str
    section_path: str | None
    snippet: str
    score: float
    source: str           # 'vec' | 'fts' | 'hybrid'


def _has_vec(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'chunks_vec'"
    ).fetchone()
    return row is not None


def _vec_search(query_vec: list[float], k: int) -> list[Hit]:
    conn = get_conn()
    if not _has_vec(conn):
        return []
    packed = struct.pack(f"<{len(query_vec)}f", *query_vec)
    rows = conn.execute(
        "SELECT v.chunk_id, v.distance, c.document_id, "
        "       c.section_path, c.text_redacted "
        "FROM chunks_vec v "
        "JOIN chunks c ON c.id = v.chunk_id "
        "WHERE v.embedding MATCH ? AND k = ? "
        "ORDER BY v.distance",
        (packed, k),
    ).fetchall()
    return [
        Hit(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            section_path=r["section_path"],
            snippet=(r["text_redacted"] or "")[:400],
            score=1.0 / (1.0 + (r["distance"] or 0.0)),
            source="vec",
        )
        for r in rows
    ]


def _fts_search(query_text: str, k: int) -> list[Hit]:
    conn = get_conn()
    # Wrap in phrase quotes so FTS5 treats the whole string as a literal
    # phrase, preventing AND/OR/NOT/* operator injection.
    safe = '"' + query_text.replace('"', '""') + '"'
    rows = conn.execute(
        "SELECT f.chunk_id, f.section_path, c.document_id, c.text_redacted, "
        "       bm25(chunks_fts) AS score "
        "FROM chunks_fts f "
        "JOIN chunks c ON c.id = f.chunk_id "
        "WHERE chunks_fts MATCH ? "
        "ORDER BY score LIMIT ?",
        (safe, k),
    ).fetchall()
    out: list[Hit] = []
    for r in rows:
        # BM25 returns negative numbers; lower (more negative) = better.
        # Flip sign for our 0-1 normalization downstream.
        out.append(Hit(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            section_path=r["section_path"],
            snippet=(r["text_redacted"] or "")[:400],
            score=1.0 / (1.0 + abs(r["score"] or 0.0)),
            source="fts",
        ))
    return out


def _rrf(hit_lists: list[list[Hit]], k: int = 60) -> list[Hit]:
    """Reciprocal rank fusion. Returns hits with combined scores."""
    combined: dict[str, dict] = {}
    for hits in hit_lists:
        for rank, h in enumerate(hits):
            score = 1.0 / (k + rank + 1)
            entry = combined.setdefault(h.chunk_id, {
                "hit": h, "score": 0.0,
            })
            entry["score"] += score
    fused: list[Hit] = []
    for cid, e in combined.items():
        h = e["hit"]
        fused.append(Hit(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            section_path=h.section_path,
            snippet=h.snippet,
            score=e["score"],
            source="hybrid",
        ))
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused


def hybrid_search(query: str, *, k: int = 12,
                  type_filter: str | None = None) -> list[Hit]:
    """Run vec + FTS + RRF, return top-k Hits.

    `type_filter` (e.g. "Service") is applied AFTER fusion by filtering
    out chunks whose document_id has no linked entity of the requested
    type. Cheap because we keep this list narrow.
    """
    # Embed the query locally.
    try:
        from app.ingest.embedder import embed_query
        qvec = embed_query(query)
    except Exception:
        qvec = None

    vec_hits = _vec_search(qvec, k * 2) if qvec else []
    fts_hits = _fts_search(query, k * 2)
    fused = _rrf([vec_hits, fts_hits])

    if type_filter:
        fused = _filter_by_entity_type(fused, type_filter)
    return fused[:k]


def _filter_by_entity_type(hits: list[Hit], type_: str) -> list[Hit]:
    if not hits:
        return hits
    chunk_ids = [h.chunk_id for h in hits]
    placeholders = ",".join("?" * len(chunk_ids))
    rows = get_conn().execute(
        f"SELECT DISTINCT ec.chunk_id "
        f"FROM entity_chunks ec "
        f"JOIN entities e ON e.id = ec.entity_id "
        f"WHERE e.type = ? AND ec.chunk_id IN ({placeholders})",
        (type_, *chunk_ids),
    ).fetchall()
    keep = {r["chunk_id"] for r in rows}
    return [h for h in hits if h.chunk_id in keep]


def fts_only_fallback(query: str, k: int = 12) -> list[Hit]:
    """Useful when the embedder isn't available (Python 3.9 setup,
    sentence-transformers not loaded, etc.)."""
    return _fts_search(query, k)
