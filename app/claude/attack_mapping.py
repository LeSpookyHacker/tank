"""ATT&CK mapping report.

For each threat in every latest TM, Sonnet assigns a MITRE technique
(tactic + technique id + name). Output is a matrix of
`(service, tactic, technique, exposure, covering_detections)`.
"""
from __future__ import annotations

import json
import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.detections import find_for_technique
from app.redact.engine import apply_redactions
from app.schemas import AttackMappingReport, AttackMappingRow
from app.storage import entities_store, threat_models_store

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
