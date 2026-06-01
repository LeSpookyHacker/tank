"""Per-TM partial results for a batched attack_mapping fan-out.

Each per-result handler appends one row (keyed by `(batch_job_id,
custom_id)` to dedup if the batch retries a request). The finalizer
reads the full set, post-processes (detection lookup, coverage_summary,
top_gaps), persists one combined report, then deletes the scratch rows
for this batch.

Short-lived data — rows live for at most one batch lifetime, typically
minutes between the per-result handlers and the finalizer.
"""
from __future__ import annotations

import json
import time

from app.db import LOCK, get_conn


def insert(*, batch_job_id: str, custom_id: str,
           service_entity_id: str, rows: list[dict]) -> None:
    """Stash one TM's worth of mapping rows.

    Uses INSERT OR REPLACE because Anthropic *can* re-deliver a result
    if the polling window catches a retry — the (batch_job_id, custom_id)
    PK absorbs the duplicate cleanly.
    """
    with LOCK:
        get_conn().execute(
            "INSERT OR REPLACE INTO attack_mapping_scratch "
            "(batch_job_id, custom_id, service_entity_id, rows_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (batch_job_id, custom_id, service_entity_id,
             json.dumps(rows), time.time()),
        )


def list_for_batch(batch_job_id: str) -> list[dict]:
    """All scratch rows for a batch, oldest first."""
    rows = get_conn().execute(
        "SELECT batch_job_id, custom_id, service_entity_id, rows_json, created_at "
        "FROM attack_mapping_scratch WHERE batch_job_id = ? "
        "ORDER BY created_at ASC",
        (batch_job_id,),
    ).fetchall()
    return [
        {
            "batch_job_id": r["batch_job_id"],
            "custom_id": r["custom_id"],
            "service_entity_id": r["service_entity_id"],
            "rows": json.loads(r["rows_json"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def delete_for_batch(batch_job_id: str) -> None:
    """Drop all scratch rows for a batch. Called by the finalizer."""
    with LOCK:
        get_conn().execute(
            "DELETE FROM attack_mapping_scratch WHERE batch_job_id = ?",
            (batch_job_id,),
        )
