"""Security philosophy doc — a long-running document Tank helps curate.

Seeded at Day 30 anniversary from decisions, threats, and tabletops
made in the first month. Evolves at Day 60, 90, 180, 365 — Sonnet
suggests additional stances based on what's changed.

Persists as a special Report (`kind='philosophy'`), referenced by
`app_state.philosophy_doc_id`.
"""
from __future__ import annotations

import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.role import get_state, tenure_day
from app.schemas import PhilosophyDoc
from app.storage import decisions_store, reports_store, tabletops_store

log = logging.getLogger("tank.philosophy")


def seed() -> str | None:
    """Initial seeding (call at Day-30). Returns the report id."""
    return _generate(label="seed", prompt_name="philosophy_seed")


def evolve() -> str | None:
    """Quarterly update (call at Day-60/90/180/365). Returns report id."""
    return _generate(label="evolve", prompt_name="philosophy_evolve")


def _generate(*, label: str, prompt_name: str) -> str | None:
    state = get_state()
    decisions = decisions_store.recent(days=90, limit=40)
    tabletops = tabletops_store.list_all(limit=10)

    decisions_text = "\n".join(
        f"- {d['title']} [{d['kind']}/{d['status']}]: "
        f"{d.get('body_md_redacted') or ''}"
        for d in decisions
    )
    tabletops_text = "\n".join(
        f"- {t['scenario_md'].split(chr(10))[0][:120]}"
        for t in tabletops
    )

    client = get_client()
    try:
        prompt = load_prompt(prompt_name)
    except FileNotFoundError:
        log.warning("%s prompt missing", prompt_name)
        return None
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=3072,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "text",
                 "text": f"# Decisions made (last 90 days)\n{decisions_text}"},
                {"type": "text",
                 "text": f"# Tabletops run\n{tabletops_text}"},
                {"type": "text",
                 "text": f"Day {tenure_day()}: produce the philosophy "
                         f"doc ({label})."},
            ]}],
            output_format=PhilosophyDoc,
        )
        log_token_usage("philosophy.generate", MODEL, getattr(resp, "usage", None))
        usage = getattr(resp, "usage", None)
        parsed = getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("philosophy %s failed: %s", label, exc)
        return None
    if not parsed:
        return None

    md = _render(parsed)
    rid = reports_store.insert(
        kind="philosophy",
        title=f"Security philosophy — Day {tenure_day()}",
        content_md=md, content_md_redacted=md,
        role_mode=state.role_mode.value,
        model=MODEL,
        scope={"label": label, "day_n": tenure_day()},
        tokens_in=getattr(usage, "input_tokens", None) if usage else None,
        tokens_out=getattr(usage, "output_tokens", None) if usage else None,
        cache_read_in=getattr(usage, "cache_read_input_tokens", None) if usage else None,
        cache_create_in=getattr(usage, "cache_creation_input_tokens", None) if usage else None,
    )

    # Track the pointer in app_state for quick fetch.
    from app.db import LOCK, get_conn
    with LOCK:
        get_conn().execute(
            "UPDATE app_state SET philosophy_doc_id = ?, "
            "updated_at = strftime('%s','now') WHERE id = 1",
            (rid,),
        )
    return rid


def latest() -> dict | None:
    state = get_state()
    if state.philosophy_doc_id:
        return reports_store.get(state.philosophy_doc_id)
    return reports_store.latest_for_kind("philosophy")


def _render(doc: PhilosophyDoc) -> str:
    lines = ["# Security philosophy", "", doc.intro, ""]
    for s in doc.stances:
        lines.append(f"## {s.title}")
        lines.append(s.body_md)
        if s.related_decision_ids:
            lines.append("")
            lines.append(f"_related decisions: "
                         f"{', '.join(s.related_decision_ids)}_")
        lines.append("")
    if doc.open_questions:
        lines.append("## Open questions")
        for q in doc.open_questions:
            lines.append(f"- {q}")
    return "\n".join(lines)
