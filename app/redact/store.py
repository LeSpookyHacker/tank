"""Persistence layer for the redaction_map.

The map is the bridge between placeholders Claude sees and original text
that only lives on this machine. Key invariants enforced here:

1. The same original (case-insensitive, stripped) always maps to the same
   placeholder, across all documents. This is what makes the redacted KB
   queryable.
2. Secrets (`category == 'secret_token'`) are stored as a SHA-256 hash of
   the original, never as cleartext. Rehydration of secrets is impossible
   by design — the user goes back to the source doc.
3. Sequence numbers per category are dense and monotonically assigned
   based on insertion order. Reusing a number for a different original
   would break rehydration of older redacted text.
"""

from __future__ import annotations

import hashlib
import time

from app.db import LOCK, get_conn


def _normalize(s: str) -> str:
    return s.strip().lower()


def _hash_key(category: str, original: str) -> str:
    return hashlib.sha256(
        f"{category}:{_normalize(original)}".encode("utf-8")
    ).hexdigest()


def _next_n_for_category(conn, category: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM redaction_map WHERE category = ?",
        (category,),
    ).fetchone()
    return (row["n"] if row else 0) + 1


def upsert_match(category: str, original: str,
                 placeholder_fmt: str) -> str:
    """Return the placeholder for this (category, original).

    On first seeing this original-in-category we allocate a new sequence
    number, format the placeholder, and persist. On subsequent sightings
    we increment `occurrence_count` and return the existing placeholder.
    """
    sha = _hash_key(category, original)
    conn = get_conn()
    with LOCK:
        existing = conn.execute(
            "SELECT placeholder FROM redaction_map "
            "WHERE sha256 = ? AND category = ?",
            (sha, category),
        ).fetchone()

        if existing is not None:
            conn.execute(
                "UPDATE redaction_map "
                "SET occurrence_count = occurrence_count + 1 "
                "WHERE placeholder = ?",
                (existing["placeholder"],),
            )
            return existing["placeholder"]

        n = _next_n_for_category(conn, category)
        placeholder = placeholder_fmt.format(n=n)

        # Secret tokens never store cleartext.
        stored = (hashlib.sha256(original.encode("utf-8")).hexdigest()
                  if category == "secret_token" else original)

        conn.execute(
            "INSERT INTO redaction_map "
            "(placeholder, category, sha256, original_text, "
            " first_seen_at, occurrence_count) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (placeholder, category, sha, stored, time.time()),
        )
        return placeholder


def load_rehydration_map(placeholders: set[str] | None = None
                         ) -> dict[str, str]:
    """Return placeholder -> original_text for rehydration.

    If `placeholders` is given, only those entries are returned (faster
    for large redaction maps). Secret-token entries are omitted because
    we can't rehydrate them — caller will see the placeholder as-is.
    """
    conn = get_conn()
    if placeholders:
        marks = ",".join("?" * len(placeholders))
        sql = (
            f"SELECT placeholder, original_text FROM redaction_map "
            f"WHERE category != 'secret_token' "
            f"AND placeholder IN ({marks})"
        )
        rows = conn.execute(sql, tuple(placeholders)).fetchall()
    else:
        rows = conn.execute(
            "SELECT placeholder, original_text FROM redaction_map "
            "WHERE category != 'secret_token'"
        ).fetchall()
    return {r["placeholder"]: r["original_text"] for r in rows}


def category_summary() -> list[dict]:
    """Used by the audit UI: counts per category."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT category, "
        "       COUNT(*) AS unique_count, "
        "       SUM(occurrence_count) AS total_occurrences "
        "FROM redaction_map "
        "GROUP BY category "
        "ORDER BY total_occurrences DESC"
    ).fetchall()
    return [dict(r) for r in rows]
