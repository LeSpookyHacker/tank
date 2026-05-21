"""Backup ledger for the SQLite snapshots written weekly by the
scheduler. Used to enforce retention (keep N most recent).
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from app.db import LOCK, get_conn


def record(path: Path, size_bytes: int, status: str = "ok") -> str:
    bid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO backup_log (id, path, size_bytes, created_at, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (bid, str(path), size_bytes, time.time(), status),
        )
    return bid


def list_recent(limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM backup_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def stale(keep_n: int = 8) -> list[dict]:
    """Backups beyond the retention window — caller deletes them."""
    rows = get_conn().execute(
        "SELECT * FROM backup_log WHERE status = 'ok' "
        "ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows[keep_n:]]


def delete_record(backup_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute("DELETE FROM backup_log WHERE id = ?", (backup_id,))
