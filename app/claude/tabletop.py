"""Tabletop exercise generator.

Given a service + a threat (from its TM, or a free-form scenario hook),
Sonnet generates: a 1-paragraph scenario, 4-6 timed injects with
expected response, facilitation notes, and an evaluation rubric.

After the exercise runs, lessons are captured and surfaced in the
lessons-learned DB (Phase 15).
"""
from __future__ import annotations

import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import get_card
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import TabletopScenario
from app.storage import tabletops_store

log = logging.getLogger("tank.tabletop")


def generate(*, service_id: str | None,
             threat_kind: str | None,
             scenario_hook: str | None = None) -> str:
    """Generate a tabletop scenario. Returns tabletop_id."""
    payload = _generate(service_id, threat_kind, scenario_hook)
    if payload is None:
        raise RuntimeError("tabletop generation returned no output")

    scenario_md_red = _render(payload)
    scenario_md = rehydrate(scenario_md_red, load_rehydration_map())

    injects_payload = [inj.model_dump() for inj in payload.injects]
    return tabletops_store.create(
        scenario_md=scenario_md,
        scope_service_id=service_id,
        threat_kind=threat_kind,
        injects=injects_payload,
    )


def _generate(service_id: str | None, threat_kind: str | None,
              scenario_hook: str | None) -> TabletopScenario | None:
    client = get_client()
    try:
        prompt = load_prompt("tabletop_generator")
    except FileNotFoundError:
        log.warning("tabletop_generator prompt missing")
        return None

    parts = []
    if service_id:
        card = get_card(service_id)
        if card:
            parts.append(f"## Service in scope\n"
                         f"Name: {apply_redactions(card['name']).redacted_text}\n"
                         f"Description: {apply_redactions(card.get('description') or '').redacted_text or '—'}\n"
                         f"Attrs: {card.get('attrs')}")
    if threat_kind:
        parts.append("## Threat / tactic\n"
                     + apply_redactions(threat_kind).redacted_text)
    if scenario_hook:
        parts.append("## Hook (optional)\n"
                     + apply_redactions(scenario_hook).redacted_text)

    user_text = "\n\n".join(parts) if parts else "Pick any plausible scenario."

    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=3072,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": [
                           {"type": "text", "text": user_text},
                           {"type": "text",
                            "text": "Produce a tabletop scenario with "
                                    "4-6 injects, facilitation notes, "
                                    "and an evaluation rubric."},
                       ]}],
            output_format=TabletopScenario,
        )
        log_token_usage("tabletop.generate", MODEL, getattr(resp, "usage", None))
        return getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("tabletop generation failed: %s", exc)
        return None


def _render(payload: TabletopScenario) -> str:
    lines = [f"# {payload.title}", "", payload.scenario_md, ""]
    lines.append("## Injects")
    for inj in payload.injects:
        lines.append(f"### +{inj.minute} min — {inj.inject}")
        if inj.expected_response:
            lines.append(f"_expected: {inj.expected_response}_")
        lines.append("")
    lines.extend(["## Facilitation notes", payload.facilitation_notes, ""])
    lines.append("## Evaluation rubric")
    for item in payload.evaluation_rubric:
        lines.append(f"- {item}")
    return "\n".join(lines)


def capture_lessons(tt_id: str, lessons_md: str,
                    tags: list[str] | None = None) -> list[str]:
    """Mark the tabletop as run and propagate lessons to lessons DB."""
    tabletops_store.mark_ran(tt_id, lessons_md=lessons_md)
    try:
        from app.storage import lessons_store
    except Exception:
        return []
    # Split lessons_md by leading "- " bullets, one row per bullet.
    bullets = [line[2:].strip() for line in lessons_md.splitlines()
               if line.strip().startswith("- ")]
    if not bullets:
        bullets = [lessons_md.strip()]
    ids = []
    for body in bullets:
        if not body:
            continue
        title = body.split(".")[0][:120]
        lid = lessons_store.create(
            title=title, body_md=body,
            source_kind="tabletop", source_id=tt_id,
            tags=tags or [],
        )
        ids.append(lid)
    return ids
