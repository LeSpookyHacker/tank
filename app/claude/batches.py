"""Anthropic Message Batches API wrapper for non-interactive Sonnet/Haiku jobs.

The Batches API charges 50% of the standard per-token rates in exchange
for async delivery (results within 24h; in practice usually < 1h). Tank
uses it for the scheduler's nightly + weekly fan-out workloads where
the user is not waiting on the result:

- `_fire_auto_briefs`: up to 5 meeting-prep briefs per night
  (handler: `meeting_prep_brief`).
- (follow-up) `_run_due_subscriptions`: due report subscriptions fired
  one batch per digest tick (handler: `report_subscription`).
- (follow-up) `_maybe_anniversary`: generic retro + security retro +
  philosophy seed/evolve at tenure milestones.
- (follow-up) `attack_mapping.generate`: one request per Threat Model
  (today's N+1 loop is the strongest fan-out case).

Architecture
------------

Three layers:

1. `submit(kind, requests, payload)` — wraps `messages.batches.create`,
   persists a `batch_jobs` row, returns the tank-side row id.
2. `poll_inflight()` — called once per scheduler tick. Walks every
   non-terminal `batch_jobs` row, refreshes its status, and when a batch
   ends invokes the kind-specific handler on each result.
3. `@register(kind)` decorator — every consumer module registers a
   handler `(custom_id, message, payload) -> None` at import time.
   Handlers do the post-processing (redact/rehydrate, persist to the
   appropriate store, publish events).

Privacy
-------

The Anthropic API contract still holds: all message contents passed to
`submit()` MUST already be pre-redacted (matches the existing
`apply_redactions` invariant). Handler outputs are rehydrated locally
before persisting to display columns.

Token accounting
----------------

Per-result usage is captured via `log_token_usage(f"batches.{kind}", ...)`
inside the result loop, mirroring the synchronous call sites. So
`/api/usage/cost` shows batch spend as ordinary `api_calls` rows.

Migration pattern (per consumer module)
---------------------------------------

`messages.batches.create` accepts raw params — no `output_format` typed
parse. Modules that today use `client.messages.parse(output_format=...)`
need an adapter to hand-back structured output via one of:

1. Tool-use mode — declare a single tool whose JSON Schema is the
   target Pydantic class. Force the model with
   `tool_choice={"type": "tool", "name": "..."}`. Read the tool input
   from the response and validate via `Cls.model_validate(...)`.
2. JSON-in-text — instruct the model to emit a JSON object and parse
   it manually. Less robust but simpler to wire up.

A consumer module should:

    @batches.register("auto_briefs")
    def _handle_auto_brief(custom_id: str, msg, payload: dict) -> None:
        # Parse msg.content (tool_use or text), redact/rehydrate,
        # persist via the module's store, publish events.
        ...

    def schedule_batch(meetings: list[dict]) -> str | None:
        requests = [
            {
                "custom_id": meeting["id"],
                "params": {
                    "model": HAIKU_MODEL,
                    "max_tokens": 4096,
                    "system": [...],   # same cached blocks as the sync path
                    "messages": [...],
                    "tools": [{"name": "emit_brief", "input_schema": ...}],
                    "tool_choice": {"type": "tool", "name": "emit_brief"},
                },
            }
            for meeting in meetings
        ]
        return batches.submit(kind="auto_briefs", requests=requests,
                              payload={"meeting_ids": [m["id"] for m in meetings]})

The synchronous path stays in place for user-facing requests (chat,
interactive report generation) — batches are strictly for background
fan-out where 1h latency is acceptable in exchange for 50% cost.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable

from app.claude.event_bus import publish
from app.config import get_client, log_token_usage
from app.db import LOCK, get_conn

log = logging.getLogger("tank.batches")

# Handler registry: kind -> (custom_id, anthropic_message, payload_dict) -> None
_HANDLERS: dict[str, Callable[[str, Any, dict], None]] = {}

# Finalizer registry: kind -> (payload, stats_dict) -> None
# Runs AFTER all per-result handlers in a batch have been dispatched.
# Used by aggregator patterns (e.g. attack_mapping fan-out) where the
# per-result handler stashes partial state in a scratch table and the
# finalizer reads the union to produce one combined output. Optional —
# kinds without an aggregation step don't register one.
_FINALIZERS: dict[str, Callable[[dict, dict], None]] = {}

# Terminal Anthropic batch processing states. Anything else means
# in-flight or still queueing.
_TERMINAL = {"ended", "failed", "cancelled", "expired"}


def register(kind: str) -> Callable:
    """Decorator: bind a post-processing function to a batch kind."""
    def deco(fn: Callable[[str, Any, dict], None]) -> Callable:
        _HANDLERS[kind] = fn
        return fn
    return deco


def register_finalizer(kind: str) -> Callable:
    """Decorator: bind a finalizer to a batch kind.

    Finalizers run once per batch after every per-result handler has
    been dispatched. Signature: `(payload: dict, stats: dict) -> None`
    where stats is `{"succeeded": N, "errored": M, "batch_job_id": id}`.
    Errors in finalizers are caught and logged; they don't roll back
    the per-result handlers' writes.
    """
    def deco(fn: Callable[[dict, dict], None]) -> Callable:
        _FINALIZERS[kind] = fn
        return fn
    return deco


_MAX_BATCH_REQUESTS = 100  # hard cap per submission to limit runaway spend


def submit(*, kind: str, requests: list[dict],
           payload: dict | None = None) -> str | None:
    """Submit a batch and persist a tracking row.

    `requests` is a list of `{custom_id, params}` dicts in the shape
    `messages.batches.create` accepts. `kind` must be a registered
    handler. `payload` is opaque JSON the handler will read.

    Returns the tank-side row id, or None on empty input / submission
    failure (caller already logged the upstream error).
    """
    if not requests:
        return None
    if len(requests) > _MAX_BATCH_REQUESTS:
        log.warning(
            "batch submit (kind=%s) truncated %d → %d (max %d)",
            kind, len(requests), _MAX_BATCH_REQUESTS, _MAX_BATCH_REQUESTS,
        )
        requests = requests[:_MAX_BATCH_REQUESTS]
    if kind not in _HANDLERS:
        raise ValueError(f"no batch handler registered for kind={kind!r}")
    client = get_client()
    try:
        batch = client.messages.batches.create(requests=requests)
    except Exception as exc:
        log.warning("batch submit (kind=%s) failed: %s", kind, exc)
        return None

    row_id = uuid.uuid4().hex
    now = time.time()
    with LOCK:
        get_conn().execute(
            "INSERT INTO batch_jobs (id, anthropic_id, kind, status, "
            " request_count, created_at, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row_id, batch.id, kind, batch.processing_status,
             len(requests), now, json.dumps(payload or {})),
        )
    publish("batches.global", "batch_submitted",
            {"id": row_id, "kind": kind, "count": len(requests)})
    log.info("submitted batch kind=%s id=%s requests=%d",
             kind, batch.id, len(requests))
    return row_id


def poll_inflight() -> None:
    """Refresh every in-flight batch; process results for newly-ended ones.

    Called from the scheduler tick — every ~60s. Cheap when nothing is
    in-flight (one SELECT, no API call).
    """
    inflight = _list_inflight()
    if not inflight:
        return
    client = get_client()
    for row in inflight:
        try:
            batch = client.messages.batches.retrieve(row["anthropic_id"])
        except Exception as exc:
            log.warning("retrieve batch %s failed: %s",
                        row["anthropic_id"], exc)
            continue
        status = batch.processing_status
        if status != row["status"]:
            _update_status(row["id"], status)
        if status == "ended" and row["status"] != "ended":
            _process_results({**row, "status": status}, client)


def _list_inflight() -> list[dict]:
    with LOCK:
        cur = get_conn().execute(
            "SELECT id, anthropic_id, kind, status, payload_json "
            "FROM batch_jobs "
            "WHERE status NOT IN ('ended', 'failed', 'cancelled', 'expired') "
            "ORDER BY created_at ASC"
        )
        return [dict(r) for r in cur.fetchall()]


def _update_status(row_id: str, status: str) -> None:
    with LOCK:
        get_conn().execute(
            "UPDATE batch_jobs SET status=? WHERE id=?",
            (status, row_id),
        )


def _process_results(row: dict, client) -> None:
    handler = _HANDLERS.get(row["kind"])
    if handler is None:
        log.warning("no handler for kind=%s on batch %s; skipping",
                    row["kind"], row["id"])
        return
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    succeeded = errored = 0
    try:
        for result in client.messages.batches.results(row["anthropic_id"]):
            r_type = getattr(result.result, "type", None)
            if r_type == "succeeded":
                msg = result.result.message
                # Token accounting first — even if the handler crashes,
                # we want spend recorded.
                log_token_usage(
                    f"batches.{row['kind']}",
                    getattr(msg, "model", "unknown"),
                    getattr(msg, "usage", None),
                )
                try:
                    handler(result.custom_id, msg, payload)
                    succeeded += 1
                except Exception:
                    log.exception("handler kind=%s custom_id=%s failed",
                                  row["kind"], result.custom_id)
                    errored += 1
            else:
                log.warning("batch result custom_id=%s type=%s",
                            result.custom_id, r_type)
                errored += 1
    except Exception as exc:
        log.warning("results iteration for batch %s failed: %s",
                    row["anthropic_id"], exc)
        return
    summary = f"succeeded={succeeded} errored={errored}"
    with LOCK:
        get_conn().execute(
            "UPDATE batch_jobs SET completed_at=?, result_summary=? WHERE id=?",
            (time.time(), summary, row["id"]),
        )

    # Aggregator step: per-result handlers may have stashed partial state
    # in a scratch table; the finalizer assembles it into a final output
    # (one report, one event, etc.). Runs after the per-result loop so
    # all writes are visible.
    finalizer = _FINALIZERS.get(row["kind"])
    if finalizer is not None:
        try:
            finalizer(payload, {"succeeded": succeeded, "errored": errored,
                                "batch_job_id": row["id"]})
        except Exception as exc:
            log.warning("finalizer kind=%s batch=%s failed: %s",
                        row["kind"], row["id"], exc)

    publish("batches.global", "batch_completed",
            {"id": row["id"], "kind": row["kind"], "summary": summary})
