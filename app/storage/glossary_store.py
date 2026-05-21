"""CRUD for the glossary builder.

Glossary terms are company-specific jargon (project names, internal
service nicknames, acronyms) extracted from the KB and confirmed by
the user. They're NOT PII — they exist to enrich Tank's chat replies
with company-specific vocabulary.
"""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def _norm(term: str) -> str:
    return term.strip().lower()


def upsert(*, term: str, definition: str,
           aliases: list[str] | None = None,
           first_seen_doc_id: str | None = None,
           confirmed: bool = False) -> str:
    norm = _norm(term)
    conn = get_conn()
    existing = conn.execute(
        "SELECT id, occurrences FROM glossary WHERE term_normalized = ?",
        (norm,),
    ).fetchone()
    now = time.time()
    if existing:
        with LOCK:
            conn.execute(
                "UPDATE glossary SET definition = ?, aliases = ?, "
                "confirmed = ?, occurrences = ?, updated_at = ? "
                "WHERE id = ?",
                (definition,
                 json.dumps(aliases or []),
                 1 if confirmed else existing["confirmed"] if False else (1 if confirmed else 0),
                 existing["occurrences"] + 1, now, existing["id"]),
            )
        return existing["id"]
    gid = uuid.uuid4().hex
    with LOCK:
        conn.execute(
            "INSERT INTO glossary "
            "(id, term, term_normalized, definition, aliases, confirmed, "
            " first_seen_doc_id, occurrences, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (gid, term, norm, definition,
             json.dumps(aliases or []),
             1 if confirmed else 0,
             first_seen_doc_id, now),
        )
    return gid


def confirm(term_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE glossary SET confirmed = 1, updated_at = ? WHERE id = ?",
            (time.time(), term_id),
        )


def reject(term_id: str) -> None:
    """Hard delete a rejected candidate."""
    conn = get_conn()
    with LOCK:
        conn.execute("DELETE FROM glossary WHERE id = ?", (term_id,))


def list_pending(limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM glossary WHERE confirmed = 0 "
        "ORDER BY occurrences DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def list_confirmed(limit: int = 500) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM glossary WHERE confirmed = 1 "
        "ORDER BY term_normalized LIMIT ?",
        (limit,),
    ).fetchall()
    return [_hydrate(r) for r in rows]


def get(term_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM glossary WHERE id = ?", (term_id,),
    ).fetchone()
    return _hydrate(row) if row else None


def _hydrate(row) -> dict:
    d = dict(row)
    try:
        d["aliases"] = json.loads(d.get("aliases") or "[]")
    except Exception:
        d["aliases"] = []
    return d
