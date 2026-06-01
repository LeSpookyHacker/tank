"""ATT&CK mapping report.

For each threat in every latest TM, Sonnet assigns a MITRE technique
(tactic + technique id + name). Output is a matrix of
`(service, tactic, technique, exposure, covering_detections)`.

Two execution paths:

- `generate()` — synchronous, N+1 Sonnet calls in a loop. Used by the
  HTTP route `POST /api/reports/attack_mapping` (caller is waiting).
- `schedule_batch()` + `@batches.register("attack_mapping_per_tm")` +
  `@batches.register_finalizer("attack_mapping_per_tm")` — submit one
  batch with N requests (one per TM), per-result handlers stash partial
  rows in `attack_mapping_scratch`, finalizer aggregates and persists
  ONE report under `kind="attack_mapping"`. Used by scheduler-driven
  subscriptions where ~1h delivery latency is acceptable in exchange
  for 50% off both input + output rates.
"""
from __future__ import annotations

import json
import logging

from app.claude import batches
from app.claude.batch_helpers import extract_validated, tool_params_for
from app.claude.event_bus import publish
from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.detections import find_for_technique
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.role import get_state
from app.schemas import AttackMappingReport, AttackMappingRow
from app.storage import (attack_mapping_scratch_store, entities_store,
                         reports_store, threat_models_store)

log = logging.getLogger("tank.attack_mapping")


def generate() -> AttackMappingReport:
    """Build the ATT&CK mapping report from latest TMs."""
    tms = threat_models_store.list_all_latest()
    rows: list[AttackMappingRow] = []

    client = get_client()
    try:
        prompt = load_prompt("report_attack_mapping")
    except FileNotFoundError:
        prompt = (
            "For each threat, assign a MITRE ATT&CK tactic + technique "
            "id + technique name. Return one row per threat."
        )

    for tm in tms:
        svc = entities_store.get_entity(tm["service_entity_id"])
        if not svc:
            continue
        threats = tm.get("threats") or []
        if not threats:
            continue

        # Compact threats text for Sonnet
        threats_text = "\n".join(
            f"- [{i}] {t.get('stride_category')}: "
            f"{apply_redactions(t.get('title') or '').redacted_text} — "
            f"{apply_redactions(t.get('description') or '').redacted_text[:200]}"
            for i, t in enumerate(threats)
        )

        try:
            resp = client.messages.parse(
                model=MODEL,
                max_tokens=2048,
                system=[{"type": "text", "text": prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": [
                    {"type": "text",
                     "text": f"## Service: {apply_redactions(svc['name']).redacted_text}\n\n"
                             f"## Threats\n{threats_text}\n\n"
                             "Map each threat to MITRE ATT&CK."},
                ]}],
                output_format=AttackMappingReport,
            )
            log_token_usage("attack_mapping.generate", MODEL, getattr(resp, "usage", None))
            chunk = getattr(resp, "parsed_output", None)
            if chunk:
                for r in chunk.rows:
                    # Override service_name to be authoritative
                    r.service_name = svc["name"]
                    # Annotate detections from KB
                    covering = find_for_technique(r.technique_id)
                    r.detections = [d["name"] for d in covering.get("detections", [])]
                    rows.append(r)
        except Exception as exc:
            log.warning("attack_mapping for %s failed: %s",
                        svc.get("name"), exc)

    gaps = [
        f"{r.service_name} / {r.technique_id} ({r.technique_name})"
        for r in rows if not r.detections and r.exposure in ("high", "medium")
    ][:10]
    summary = (
        f"{len(rows)} threat→ATT&CK mappings across {len(tms)} services. "
        f"{len(gaps)} mapped threats have no covering detection."
    )
    return AttackMappingReport(
        rows=rows, coverage_summary=summary, top_gaps=gaps,
    )


# ─── Batch path (one request per TM, finalizer aggregates) ────────────

def _prompt() -> str:
    try:
        return load_prompt("report_attack_mapping")
    except FileNotFoundError:
        return (
            "For each threat, assign a MITRE ATT&CK tactic + technique "
            "id + technique name. Return one row per threat."
        )


def _request_for_tm(tm: dict, svc: dict) -> dict | None:
    """Build one batch request for a single TM. Mirrors the per-TM
    body of `generate()` so the cached system prompt hits the same
    cache entry across sync and batch paths.
    """
    threats = tm.get("threats") or []
    if not threats:
        return None
    threats_text = "\n".join(
        f"- [{i}] {t.get('stride_category')}: "
        f"{apply_redactions(t.get('title') or '').redacted_text} — "
        f"{apply_redactions(t.get('description') or '').redacted_text[:200]}"
        for i, t in enumerate(threats)
    )
    tools, tool_choice = tool_params_for(AttackMappingReport)
    return {
        "custom_id": tm["id"],
        "params": {
            "model": MODEL,
            "max_tokens": 2048,
            "system": [{"type": "text", "text": _prompt(),
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [
                {"type": "text",
                 "text": f"## Service: {apply_redactions(svc['name']).redacted_text}\n\n"
                         f"## Threats\n{threats_text}\n\n"
                         "Map each threat to MITRE ATT&CK."},
            ]}],
            "tools": tools,
            "tool_choice": tool_choice,
        },
    }


def schedule_batch() -> str | None:
    """Submit one batch with one request per latest TM.

    Returns the batch_jobs row id (so the finalizer can read scratch
    rows for that id), or None if there's nothing to map.
    """
    tms = threat_models_store.list_all_latest()
    requests = []
    tm_meta: dict[str, dict] = {}
    for tm in tms:
        svc = entities_store.get_entity(tm["service_entity_id"])
        if not svc:
            continue
        req = _request_for_tm(tm, svc)
        if req is None:
            continue
        requests.append(req)
        tm_meta[tm["id"]] = {
            "service_entity_id": tm["service_entity_id"],
            "service_name": svc["name"],
        }
    if not requests:
        return None
    return batches.submit(
        kind="attack_mapping_per_tm",
        requests=requests,
        payload={
            "tm_meta": tm_meta,
            "tm_count": len(tm_meta),
        },
    )


@batches.register("attack_mapping_per_tm")
def _handle_per_tm(custom_id: str, msg, payload: dict) -> None:
    """Stash one TM's mapping rows in the scratch table for the finalizer."""
    parsed = extract_validated(msg, AttackMappingReport)
    if parsed is None:
        return
    meta = (payload.get("tm_meta") or {}).get(custom_id, {})
    service_entity_id = meta.get("service_entity_id", "")
    authoritative_name = meta.get("service_name", "")
    rows_out: list[dict] = []
    for r in parsed.rows:
        # Override service_name to be authoritative (matches sync path).
        r_dict = r.model_dump()
        if authoritative_name:
            r_dict["service_name"] = authoritative_name
        rows_out.append(r_dict)
    # `payload["batch_job_id"]` is injected by the finalizer-aware hook
    # below — but for per-result we read it out of stats indirectly via
    # a payload key we set when submitting. Simpler: use the message-
    # local payload + look up by custom_id later. We key scratch by
    # batch_job_id which is in `stats` only at finalizer time, so we
    # must derive it here from the in-flight batch_jobs row.
    #
    # Workaround: payload doesn't carry batch_job_id at submit time.
    # We look up the most recent in-flight batch for this kind that
    # contains this custom_id. To avoid that complexity, we instead
    # write scratch rows keyed by `custom_id` alone for now and have
    # the finalizer pass `batch_job_id` into a lookup. But our scratch
    # PK is (batch_job_id, custom_id) — so we need batch_job_id here.
    #
    # Resolve by reading the latest non-terminal batch row for this
    # kind whose payload references this custom_id.
    batch_job_id = _find_batch_job_id_for(custom_id, "attack_mapping_per_tm")
    if batch_job_id is None:
        log.warning("attack_mapping per_tm %s: no in-flight batch found",
                    custom_id)
        return
    attack_mapping_scratch_store.insert(
        batch_job_id=batch_job_id,
        custom_id=custom_id,
        service_entity_id=service_entity_id,
        rows=rows_out,
    )


def _find_batch_job_id_for(custom_id: str, kind: str) -> str | None:
    """Look up the batch_jobs row id whose payload references custom_id.

    Used by the per-result handler because submit() doesn't know its
    own row id at request-build time (chicken-and-egg). We scan only
    in-flight batches of the given kind to keep it tight.
    """
    from app.db import LOCK, get_conn
    with LOCK:
        cur = get_conn().execute(
            "SELECT id, payload_json FROM batch_jobs "
            "WHERE kind = ? AND status NOT IN "
            "  ('ended', 'failed', 'cancelled', 'expired') "
            "ORDER BY created_at DESC",
            (kind,),
        )
        rows = cur.fetchall()
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if custom_id in (payload.get("tm_meta") or {}):
            return r["id"]
    # Fall back to most recent ended-but-just-completed batch (race
    # window where _process_results updates status before iterating).
    with LOCK:
        cur = get_conn().execute(
            "SELECT id, payload_json FROM batch_jobs "
            "WHERE kind = ? "
            "ORDER BY created_at DESC LIMIT 5",
            (kind,),
        )
        rows = cur.fetchall()
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if custom_id in (payload.get("tm_meta") or {}):
            return r["id"]
    return None


def _render_md(parsed: AttackMappingReport) -> str:
    lines = ["# ATT&CK mapping", "", parsed.coverage_summary, ""]
    if parsed.top_gaps:
        lines.append("## Top gaps (exposed but uncovered)")
        for g in parsed.top_gaps:
            lines.append(f"- {g}")
        lines.append("")
    lines.append("| Service | Tactic | Technique | Exposure | Detections |")
    lines.append("|---|---|---|---|---|")
    for r in parsed.rows:
        det = ", ".join(r.detections) if r.detections else "—"
        lines.append(f"| {r.service_name} | {r.tactic} | "
                     f"{r.technique_id} {r.technique_name} | "
                     f"{r.exposure} | {det} |")
    return "\n".join(lines)


@batches.register_finalizer("attack_mapping_per_tm")
def _finalize_attack_mapping(payload: dict, stats: dict) -> None:
    """Aggregate scratch rows into one combined ATT&CK mapping report."""
    batch_job_id = stats["batch_job_id"]
    scratch = attack_mapping_scratch_store.list_for_batch(batch_job_id)
    if not scratch:
        log.info("attack_mapping finalizer: no scratch rows for batch %s",
                 batch_job_id)
        return
    aggregated_rows: list[AttackMappingRow] = []
    for entry in scratch:
        for r_dict in entry["rows"]:
            try:
                row = AttackMappingRow.model_validate(r_dict)
            except Exception as exc:
                log.warning("scratch row failed validation: %s", exc)
                continue
            # Annotate detections from local KB (same as sync path).
            covering = find_for_technique(row.technique_id)
            row.detections = [d["name"] for d in covering.get("detections", [])]
            aggregated_rows.append(row)
    if not aggregated_rows:
        attack_mapping_scratch_store.delete_for_batch(batch_job_id)
        log.info("attack_mapping finalizer: no usable rows; nothing to persist")
        return
    tm_count = payload.get("tm_count") or len(scratch)
    gaps = [
        f"{r.service_name} / {r.technique_id} ({r.technique_name})"
        for r in aggregated_rows
        if not r.detections and r.exposure in ("high", "medium")
    ][:10]
    summary = (
        f"{len(aggregated_rows)} threat→ATT&CK mappings across "
        f"{tm_count} services. {len(gaps)} mapped threats have no "
        f"covering detection."
    )
    combined = AttackMappingReport(
        rows=aggregated_rows, coverage_summary=summary, top_gaps=gaps,
    )
    md_redacted = _render_md(combined)
    md = rehydrate(md_redacted, load_rehydration_map())
    state = get_state()
    report_id = reports_store.insert(
        kind="attack_mapping",
        title="ATT&CK mapping",
        content_md=md,
        content_md_redacted=md_redacted,
        role_mode=state.role_mode.value,
        model=MODEL,
        scope={"batch_job_id": batch_job_id, "tm_count": tm_count},
    )
    attack_mapping_scratch_store.delete_for_batch(batch_job_id)
    publish("reports.global", "report_created",
            {"id": report_id, "kind": "attack_mapping",
             "title": "ATT&CK mapping"})
