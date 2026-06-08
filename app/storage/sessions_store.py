"""SQLite-backed session store (SEC-003).

Replaces the in-memory _SESSIONS dict in app/routers/auth.py so that
session tokens survive server restarts. Tokens are 256-bit random strings
(secrets.token_urlsafe(32)) — no brute-force risk from DB persistence.

All writes use the global LOCK; reads are lock-free (WAL mode allows
concurrent readers). Expired sessions are pruned lazily on each new login
rather than via a background job — the sessions table stays small.
"""
from __future__ import annotations

import time

from app.db import LOCK, get_conn


def create(token: str, expires_at: float) -> None:
    """Upsert a session token with its expiry epoch."""
    with LOCK:
        get_conn().execute(
            "INSERT OR REPLACE INTO sessions (token, expires_at, created_at) "
            "VALUES (?, ?, ?)",
            (token, expires_at, time.time()),
        )


def get_expiry(token: str) -> float | None:
    """Return the expiry epoch if token exists and has not expired, else None.

    Side effect: deletes the row if it has already expired (lazy cleanup).
    """
    row = get_conn().execute(
        "SELECT expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    if row is None:
        return None
    if time.time() > row["expires_at"]:
        delete(token)
        return None
    return row["expires_at"]


def delete(token: str) -> None:
    """Remove a specific session (logout)."""
    with LOCK:
        get_conn().execute("DELETE FROM sessions WHERE token = ?", (token,))


def cleanup_expired() -> None:
    """Delete all expired sessions. Called on each new login to keep the table lean."""
    with LOCK:
        get_conn().execute(
            "DELETE FROM sessions WHERE expires_at < ?", (time.time(),)
        )
