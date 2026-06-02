"""IR runbook generator.

`generate(service_entity_id, threat_scenario, severity)` builds a
five-phase runbook (detect / contain / eradicate / recover / comms)
from KB context: service card, threat model, past postmortems, IAM
policies, and detection coverage.

The resulting markdown is stored in `ir_runbooks` and optionally
back-fed into the KB as a Runbook entity so chat tools can surface it.
"""
from __future__ import annotations

import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import IRRunbookOutput
from app.storage import ir_runbooks_store

log = logging.getLogger("tank.ir_runbook")

_PHASE_ICONS = {
    "detect": "🔍",
    "contain": "🛑",
    "eradicate": "🧹",
    "recover": "♻️",
    "comms": "📢",
}


def generate(
    *,
    service_entity_id: str | None = None,
    threat_scenario: str,
    severity: str = "any",
    tabletop_id: str | None = None,
    project_id: str | None = None,
) -> str:
    """Generate a runbook and persist it. Returns runbook_id."""
    context_parts = _build_context(service_entity_id, threat_scenario)

    try:
        prompt = load_prompt("ir_runbook")
    except FileNotFoundError:
        prompt = "You are an IR engineer. Produce a structured runbook."

    client = get_client()
    system_block = {
        "type": "text", "text": prompt,
        "cache_control": {"type": "ephemeral"},
    }
    context_block = {
        "type": "text",
        "text": apply_redactions("\n\n".join(context_parts)).redacted_text,
        "cache_control": {"type": "ephemeral"},
    }
    task_text = (
        f"Threat scenario: {threat_scenario}\n"
        f"Severity trigger: {severity}\n\n"
        "Generate the IR runbook for this scenario using the KB context above."
    )

    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=8192,
            system=[system_block],
            messages=[{"role": "user", "content": [
                context_block,
                {"type": "text",
                 "text": apply_redactions(task_text).redacted_text},
            ]}],
            output_format=IRRunbookOutput,
        )
        log_token_usage("ir_runbook.generate", MODEL, getattr(resp, "usage", None))
        parsed: IRRunbookOutput = resp.parsed_output
    except Exception as exc:
        log.warning("ir_runbook generate failed: %s", exc)
        raise

    md_redacted = _render(parsed)
    md_display = rehydrate(md_redacted, load_rehydration_map())

    rid = ir_runbooks_store.create(
        threat_scenario=threat_scenario,
        runbook_md=md_display,
        runbook_md_redacted=md_redacted,
        service_entity_id=service_entity_id,
        severity_trigger=parsed.severity_trigger or severity,
        contacts=parsed.escalation_path,
        escalation=parsed.escalation_path,
        tabletop_id=tabletop_id,
        project_id=project_id,
    )

    # Feed back into KB as a Runbook entity so chat tools surface it.
    if service_entity_id:
        _register_as_entity(rid, parsed, service_entity_id)

    return rid


def _render(parsed: IRRunbookOutput) -> str:
    lines: list[str] = [
        f"# {parsed.title}",
        "",
        parsed.scenario_summary,
        f"_Severity trigger: {parsed.severity_trigger}_",
        "",
    ]

    if parsed.detection_signals:
        lines.append("## Detection signals")
        for s in parsed.detection_signals:
            lines.append(f"- {s}")
        lines.append("")

    for p in parsed.phases:
        icon = _PHASE_ICONS.get(p.phase, "•")
        lines.append(f"## {icon} {p.phase.capitalize()}")
        if p.time_box:
            lines.append(f"_Time box: {p.time_box}_")
        lines.append("")
        for step in p.steps:
            lines.append(f"1. {step}")
        if p.decision_points:
            lines.append("")
            lines.append("**Decision points:**")
            for dp in p.decision_points:
                lines.append(f"- {dp}")
        if p.success_criteria:
            lines.append("")
            lines.append(f"**Done when:** {p.success_criteria}")
        lines.append("")

    if parsed.escalation_path:
        lines.append("## Escalation path")
        for e in parsed.escalation_path:
            role = e.get("role", "?")
            trigger = e.get("trigger", "?")
            channel = e.get("channel", "?")
            lines.append(f"- **{role}** — {trigger} via {channel}")
        lines.append("")

    if parsed.comms_template:
        lines.append("## Comms template")
        lines.append("```")
        lines.append(parsed.comms_template)
        lines.append("```")

    return "\n".join(lines)


def _build_context(
    service_entity_id: str | None,
    threat_scenario: str,
) -> list[str]:
    parts: list[str] = []

    try:
        from app.kb.entities import get_card
        from app.storage import threat_models_store, postmortems_store
        from app.kb.detections import coverage_table
        from app.kb.search import hybrid_search

        if service_entity_id:
            card = get_card(service_entity_id)
            if card:
                parts.append(f"## Service: {card['name']}")
                if card.get("description"):
                    parts.append(card["description"])
                parts.append(f"attrs: {card.get('attrs')}")
                for ch in (card.get("linked_chunks") or [])[:6]:
                    parts.append(f"  chunk: {(ch.get('snippet') or '')[:300]}")
                parts.append("")

            # Operational ownership / on-call roster — anchors the
            # escalation path to the real contacts the user set.
            from app.storage import ownership_store
            own = ownership_store.get(service_entity_id)
            if own:
                from app.kb.entities import get_card as _gc
                parts.append("## Operational ownership / on-call")
                prim = _gc(own["primary_owner_entity_id"]) if own.get("primary_owner_entity_id") else None
                if prim:
                    parts.append(f"- Primary owner: {prim['name']}")
                if own.get("on_call_contact"):
                    parts.append(f"- On-call: {own['on_call_contact']}")
                if own.get("slack_channel"):
                    parts.append(f"- Slack: {own['slack_channel']}")
                if own.get("pager_handle"):
                    parts.append(f"- Pager: {own['pager_handle']}")
                for lvl in (own.get("escalation") or []):
                    parts.append(f"- Escalation {lvl.get('level','?')}: {lvl.get('contact','?')}")
                parts.append("")

            tm = threat_models_store.latest_for_service(service_entity_id)
            if tm:
                threats = tm.get("threats") or []
                parts.append(f"## Threat model v{tm['version']} ({len(threats)} threats)")
                for t in threats[:6]:
                    parts.append(
                        f"- {t.get('stride_category','?')}: {t.get('title','?')} "
                        f"(L={t.get('likelihood','?')} I={t.get('impact','?')}) "
                        f"controls: {t.get('suggested_controls', [])}"
                    )
                parts.append("")

        # Recent postmortems for context on past incidents.
        pms = postmortems_store.list_by_status("published")
        if pms:
            parts.append("## Recent postmortems")
            for pm in pms[:3]:
                fields = pm.get("fields") or {}
                parts.append(
                    f"- [{pm.get('severity','?')}] {pm['title']}: "
                    f"{fields.get('summary', '')[:200]}"
                )
            parts.append("")

        # Scenario-relevant KB chunks.
        hits = hybrid_search(threat_scenario, k=8)
        if hits:
            parts.append("## Relevant KB context")
            for h in hits:
                parts.append(f"  [{h.section_path or '?'}]: {h.snippet[:250]}")
            parts.append("")

    except Exception as exc:
        log.debug("context build failed (non-fatal): %s", exc)

    return parts


def _register_as_entity(
    runbook_id: str,
    parsed: IRRunbookOutput,
    service_entity_id: str,
) -> None:
    try:
        from app.storage import entities_store, relationships_store
        eid = entities_store.upsert_entity(
            type_="Runbook",
            name=parsed.title,
            description=parsed.scenario_summary,
            attrs={"runbook_id": runbook_id,
                   "severity_trigger": parsed.severity_trigger},
            provenance="inferred",
        )
        relationships_store.upsert_relationship(
            src_id=service_entity_id,
            dst_id=eid,
            kind="has_control",
            provenance="inferred",
        )
    except Exception as exc:
        log.debug("entity registration failed (non-fatal): %s", exc)
