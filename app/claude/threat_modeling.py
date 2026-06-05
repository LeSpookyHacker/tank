"""Versioned threat-model generation.

A "living" threat model is one that survives architectural change: when
the contributing chunks for a service mutate (new endpoint, new
dependency, new data flow), we regenerate against the previous TM and
ask Sonnet to mark each prior threat `still_valid`, `invalidated`, or
`updated`, plus surface any genuinely `new` threats. The result is a
new row in `threat_models` with the next version number.

Drift detection compares `arch_snapshot_hash` (sha256 over the
contributing chunks at generation time) against the current hash for
the service. Mismatch ⇒ regenerate.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from app.claude.caching import CACHE_1H
from app.claude.event_bus import publish
from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import get_card
from app.kb.relationships import traverse
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import ThreatModelV2
from app.storage import entities_store, threat_models_store
from app.storage.chunks_store import list_chunks_for_doc

log = logging.getLogger("tank.threat_modeling")

_PH_RE = re.compile(
    r"\[(?:EMAIL|INTERNAL_HOST|HOST|PRIVATE_IP|PUBLIC_IP|"
    r"AWS_ACCT|AWS_ARN|GCP_PROJECT|AZURE_SUB|SECRET|PERSON|CUSTOM[A-Z_]*)_\d+\]"
)


def _ph_in(text: str) -> set[str]:
    return set(_PH_RE.findall(text or ""))


def _gather_service_chunks(service_id: str, limit: int = 40) -> list[dict]:
    """Pull chunks attached (directly or via 1-hop) to a service.

    We use the entity_chunks join + the service's neighborhood (1 hop
    out via depends_on / hosted_in / stores_data_in) to give Sonnet a
    realistic picture without dumping the entire KB.
    """
    from app.db import get_conn
    chunks: list[dict] = []

    # direct entity_chunks
    rows = get_conn().execute(
        "SELECT c.id, c.text_redacted, c.section_path, c.document_id "
        "FROM chunks c JOIN entity_chunks ec ON ec.chunk_id = c.id "
        "WHERE ec.entity_id = ? LIMIT ?",
        (service_id, limit),
    ).fetchall()
    chunks.extend([dict(r) for r in rows])

    # 1-hop neighborhood chunks
    if len(chunks) < limit:
        edges = traverse(service_id, direction="both")
        neighbor_ids = {e["dst_id"] if e["src_id"] == service_id else e["src_id"]
                        for e in edges.get("edges", [])}
        if neighbor_ids:
            qmarks = ",".join("?" for _ in neighbor_ids)
            rows = get_conn().execute(
                f"SELECT c.id, c.text_redacted, c.section_path, c.document_id "
                f"FROM chunks c JOIN entity_chunks ec ON ec.chunk_id = c.id "
                f"WHERE ec.entity_id IN ({qmarks}) "
                f"LIMIT ?",
                (*neighbor_ids, limit - len(chunks)),
            ).fetchall()
            chunks.extend([dict(r) for r in rows])

    return chunks[:limit]


def _arch_snapshot_hash(chunks: list[dict]) -> str:
    """Stable hash over chunk ids — drift if the set changes."""
    ids = sorted(c["id"] for c in chunks)
    return hashlib.sha256(("|".join(ids)).encode("utf-8")).hexdigest()


def _scope_block(service_id: str, chunks: list[dict]) -> dict:
    card = get_card(service_id) or {}
    parts = [
        f"## Service: {apply_redactions(card.get('name', '(unknown)')).redacted_text}",
        f"description: {apply_redactions(card.get('description') or '').redacted_text or '—'}",
        f"attrs: {card.get('attrs')}",
        "",
        "## Contributing chunks",
    ]
    for c in chunks:
        parts.append(
            f"- chunk[{c['id']}] section={c.get('section_path') or '—'}: "
            f"{(c.get('text_redacted') or '')[:300]}"
        )
    return {
        "type": "text",
        "text": "\n".join(parts),
        "cache_control": {"type": "ephemeral"},
    }


def _prior_block(prior: dict | None) -> dict | None:
    if not prior:
        return None
    threats = prior.get("threats") or []
    parts = ["## Prior threat model (for delta)",
             f"version: {prior.get('version')}",
             f"generated_at: {prior.get('generated_at')}",
             ""]
    for i, t in enumerate(threats):
        parts.append(f"### prior[{i}] {t.get('stride_category', '?')}: {t.get('title', '')}")
        parts.append(f"likelihood={t.get('likelihood')} impact={t.get('impact')}")
        parts.append(t.get("description", ""))
        parts.append("")
    # Prior threats are stable across regens until arch drifts; 1h cache
    # means rapid back-to-back regens (or a weekly digest that touches
    # several services) pay cache-read rates instead of cold each time.
    return {"type": "text", "text": "\n".join(parts),
            "cache_control": CACHE_1H}


def _render_md(parsed: ThreatModelV2, version: int) -> str:
    lines = [f"# Threat model — {parsed.service_name} (v{version})", ""]
    lines.append(parsed.summary)
    lines.append("")
    for t in parsed.threats:
        marker = {"new": "🆕", "still_valid": "✓", "invalidated": "✗",
                  "updated": "↻"}.get(t.state, "")
        lines.append(f"## {marker} {t.stride_category}: {t.title}")
        lines.append(f"- Likelihood: **{t.likelihood}** · Impact: **{t.impact}** "
                     f"· State: `{t.state}`")
        lines.append("")
        lines.append(t.description)
        if t.suggested_controls:
            lines.append("")
            lines.append("**Suggested controls:**")
            for c in t.suggested_controls:
                lines.append(f"- {c}")
        if t.evidence_chunk_ids:
            lines.append("")
            lines.append(f"_evidence: {', '.join(t.evidence_chunk_ids)}_")
        lines.append("")
    if parsed.invalidated_prior_titles:
        lines.append("## Invalidated from prior version")
        for x in parsed.invalidated_prior_titles:
            lines.append(f"- {x}")
        lines.append("")
    if parsed.blind_spots:
        lines.append("## Blind spots")
        for b in parsed.blind_spots:
            lines.append(f"- {b}")
    return "\n".join(lines)


def generate(service_id: str) -> str:
    """Generate (or regenerate) a TM for the given service. Returns tm_id."""
    svc = entities_store.get_entity(service_id)
    if not svc or svc["type"] != "Service":
        raise ValueError(f"not a Service entity: {service_id}")

    chunks = _gather_service_chunks(service_id)
    arch_hash = _arch_snapshot_hash(chunks)
    prior = threat_models_store.latest_for_service(service_id)

    client = get_client()
    system_block = {
        "type": "text",
        "text": load_prompt("threat_model_v2"),
        # threat_model_v2 system prompt is stable across all services;
        # 1h cache covers a Sunday digest that regenerates several TMs.
        "cache_control": CACHE_1H,
    }
    user_blocks: list[dict] = [_scope_block(service_id, chunks)]
    pb = _prior_block(prior)
    if pb:
        user_blocks.append(pb)
    user_blocks.append({
        "type": "text",
        "text": "Generate a STRIDE threat model. If a prior model is "
                "provided, mark each prior threat still_valid|invalidated|"
                "updated and add any genuinely new threats. Cite evidence "
                "chunk_ids you saw in scope.",
    })

    resp = client.messages.parse(
        model=MODEL,
        max_tokens=8192,
        system=[system_block],
        messages=[{"role": "user", "content": user_blocks}],
        output_format=ThreatModelV2,
    )
    log_token_usage("threat_modeling.generate", MODEL, getattr(resp, "usage", None))
    parsed: ThreatModelV2 | None = getattr(resp, "parsed_output", None)
    if parsed is None:
        raise RuntimeError("threat_model_v2 generation returned no output")

    next_version = (prior["version"] if prior else 0) + 1
    md_red = _render_md(parsed, version=next_version)
    md = rehydrate(md_red, load_rehydration_map(_ph_in(md_red)))

    threats_payload = [t.model_dump() for t in parsed.threats]

    tm_id = threat_models_store.insert(
        service_entity_id=service_id,
        title=f"Threat model — {parsed.service_name} (v{next_version})",
        body_md=md, body_md_redacted=md_red,
        threats=threats_payload,
        arch_snapshot_hash=arch_hash,
    )
    publish("threat_models.global", "threat_model_created",
            {"id": tm_id, "service_id": service_id,
             "version": next_version})
    return tm_id


def current_arch_hash(service_id: str) -> str:
    """Compute the current arch hash for a service (without generating)."""
    return _arch_snapshot_hash(_gather_service_chunks(service_id))


def find_drift() -> list[dict]:
    """Return services whose latest TM hash differs from current."""
    drifted: list[dict] = []
    for tm in threat_models_store.list_all_latest():
        try:
            current = current_arch_hash(tm["service_entity_id"])
        except Exception:
            continue
        if current != tm["arch_snapshot_hash"]:
            svc = entities_store.get_entity(tm["service_entity_id"])
            drifted.append({
                "service_entity_id": tm["service_entity_id"],
                "service_name": svc["name"] if svc else "(unknown)",
                "tm_id": tm["id"],
                "tm_version": tm["version"],
                "prior_hash": tm["arch_snapshot_hash"],
                "current_hash": current,
            })
    return drifted
