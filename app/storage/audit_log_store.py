"""Audit log for destructive and sensitive operations."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def log_action(
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
    remote_addr: str | None = None,
) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO audit_log "
            "(id, action, resource_type, resource_id, detail_json, remote_addr, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex,
                action,
                resource_type,
                resource_id,
                json.dumps(detail) if detail else None,
                remote_addr,
                time.time(),
            ),
        )


def list_recent(limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
