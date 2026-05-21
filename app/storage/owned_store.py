"""CRUD for personal entity ownership.

The user marks entities they own / review / are consulted on /
informed about. The ownership dashboard reads from here to weight
the per-entity risk score.

Single-user assumption holds: `user_id` always defaults to 1.
"""
from __future__ import annotations

import time

from app.db import LOCK, get_conn

ALLOWED_ROLES = {"owner", "reviewer", "consulted", "informed"}


def claim(*, entity_id: str, role: str = "owner",
          user_id: int = 1) -> None:
    if role not in ALLOWED_ROLES:
        raise ValueError(f"unknown ownership role: {role}")
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO owned_entities "
            "(user_id, entity_id, role, set_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, entity_id, role, time.time()),
        )


def release(*, entity_id: str, user_id: int = 1) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "DELETE FROM owned_entities WHERE user_id = ? AND entity_id = ?",
            (user_id, entity_id),
        )


def list_owned(user_id: int = 1, role: str | None = None) -> list[dict]:
    if role:
        rows = get_conn().execute(
            "SELECT * FROM owned_entities WHERE user_id = ? AND role = ?",
            (user_id, role),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM owned_entities WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def role_for(entity_id: str, user_id: int = 1) -> str | None:
    row = get_conn().execute(
        "SELECT role FROM owned_entities WHERE user_id = ? AND entity_id = ?",
        (user_id, entity_id),
    ).fetchone()
    return row["role"] if row else None
