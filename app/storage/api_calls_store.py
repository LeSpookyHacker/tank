"""Token ledger for all Claude API call sites not covered by messages/reports."""
from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn


def record(*, call_site: str, model: str,
           tokens_in: int = 0, tokens_out: int = 0,
           cache_read_in: int = 0, cache_create_in: int = 0) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO api_calls "
            "(id, call_site, model, tokens_in, tokens_out, "
            " cache_read_in, cache_create_in, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, call_site, model,
             tokens_in, tokens_out, cache_read_in, cache_create_in,
             time.time()),
        )
