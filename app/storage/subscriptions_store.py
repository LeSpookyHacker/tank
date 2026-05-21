"""CRUD for `report_subscriptions`."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


_CADENCE_SECONDS = {
    "daily": 86400,
    "weekly": 7 * 86400,
    "monthly": 30 * 86400,
    "quarterly": 90 * 86400,
}


def subscribe(*, kind: str, cadence: str, role_mode: str,
              scope: dict | None = None) -> str:
    if cadence not in _CADENCE_SECONDS:
        raise ValueError(f"unknown cadence: {cadence}")
    sid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO report_subscriptions "
            "(id, kind, scope_json, role_mode, cadence, last_run_at, "
            " last_report_id, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, 1, ?)",
            (sid, kind, json.dumps(scope or {}), role_mode, cadence,
             time.time()),
        )
    return sid


def list_all(*, enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM report_subscriptions"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY created_at DESC"
    rows = get_conn().execute(sql).fetchall()
    return [dict(r) for r in rows]


def list_due_for_run() -> list[dict]:
    """Subscriptions whose next run window has passed."""
    now = time.time()
    out: list[dict] = []
    for r in list_all(enabled_only=True):
        elapsed_needed = _CADENCE_SECONDS[r["cadence"]]
        last = r["last_run_at"] or 0
        if (now - last) >= elapsed_needed:
            out.append(r)
    return out


def mark_run(subscription_id: str, report_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE report_subscriptions "
            "SET last_run_at = ?, last_report_id = ? WHERE id = ?",
            (time.time(), report_id, subscription_id),
        )


def set_enabled(subscription_id: str, enabled: bool) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE report_subscriptions SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, subscription_id),
        )


def delete(subscription_id: str) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "DELETE FROM report_subscriptions WHERE id = ?",
            (subscription_id,),
        )
