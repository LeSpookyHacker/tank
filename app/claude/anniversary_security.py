"""Security-focused anniversary retros.

Augments the existing generic anniversary retro (in `claude/anniversary.py`)
with a security lens: threats added, decisions made, controls covered,
detections added, incidents handled in the window.

Persisted as Report (`kind='anniversary_security_<N>'`).
"""
from __future__ import annotations

import logging
import time

from app.config import MODEL, get_client, load_prompt
from app.role import get_state, tenure_day
from app.schemas import AnniversaryRetro
from app.storage import (decisions_store, postmortems_store, reports_store,
                         threat_models_store)

log = logging.getLogger("tank.anniversary_security")


def generate(day_n: int) -> str | None:
    """Generate a security-focused retro for Day N. Returns report id."""
    state = get_state()
    if not state.tenure_started_at:
        return None

    # Build the window: last `day_n` days, or 30 if first retro.
    window_start = time.time() - day_n * 86400
    decisions = decisions_store.recent(days=day_n, limit=200)
    tms = [t for t in threat_models_store.list_all_latest()
           if t.get("generated_at", 0) >= window_start]
    pms = [p for p in postmortems_store.list_by_status("published")
           if p.get("created_at", 0) >= window_start]

    facts = (
        f"## Window: last {day_n} days\n"
        f"- Decisions made: {len(decisions)}\n"
        f"- Threat models generated/updated: {len(tms)}\n"
        f"- Postmortems published: {len(pms)}\n\n"
        "## Decisions\n"
        + "\n".join(f"- {d['title']} [{d['kind']}]" for d in decisions[:30])
        + "\n\n## Threat models\n"
        + "\n".join(f"- {t['title']} v{t['version']}" for t in tms)
        + "\n\n## Postmortems\n"
        + "\n".join(f"- {p['title']} ({p.get('severity')})" for p in pms)
    )

    client = get_client()
    try:
        prompt = load_prompt("anniversary_security")
    except FileNotFoundError:
        log.warning("anniversary_security prompt missing")
        return None
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=2500,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "text", "text": facts},
                {"type": "text",
                 "text": f"Produce the Day-{day_n} security retro."},
            ]}],
            output_format=AnniversaryRetro,
        )
        parsed = getattr(resp, "parsed_output", None)
        usage = getattr(resp, "usage", None)
    except Exception as exc:
        log.warning("anniversary_security %d failed: %s", day_n, exc)
        return None
    if not parsed:
        return None

    md = _render(parsed)
    return reports_store.insert(
        kind=f"anniversary_security_{day_n}",
        title=f"Day-{day_n} security retro",
        content_md=md, content_md_redacted=md,
        role_mode=state.role_mode.value,
        model=MODEL,
        scope={"day_n": day_n},
        tokens_in=getattr(usage, "input_tokens", 0) if usage else None,
        tokens_out=getattr(usage, "output_tokens", 0) if usage else None,
        cache_read_in=getattr(usage, "cache_read_input_tokens", 0) if usage else None,
        cache_create_in=getattr(usage, "cache_creation_input_tokens", 0) if usage else None,
    )


def build_batch_request(day_n: int) -> dict:
    """Build a single anniversary_security batch request.

    Mirrors the sync `generate()` prompt + facts assembly. Custom id is
    `security-{day_n}` so the bundle handler can dispatch.
    """
    from app.claude.batch_helpers import tool_params_for

    state = get_state()
    window_start = time.time() - day_n * 86400
    decisions = decisions_store.recent(days=day_n, limit=200)
    tms = [t for t in threat_models_store.list_all_latest()
           if t.get("generated_at", 0) >= window_start]
    pms = [p for p in postmortems_store.list_by_status("published")
           if p.get("created_at", 0) >= window_start]
    facts = (
        f"## Window: last {day_n} days\n"
        f"- Decisions made: {len(decisions)}\n"
        f"- Threat models generated/updated: {len(tms)}\n"
        f"- Postmortems published: {len(pms)}\n\n"
        "## Decisions\n"
        + "\n".join(f"- {d['title']} [{d['kind']}]" for d in decisions[:30])
        + "\n\n## Threat models\n"
        + "\n".join(f"- {t['title']} v{t['version']}" for t in tms)
        + "\n\n## Postmortems\n"
        + "\n".join(f"- {p['title']} ({p.get('severity')})" for p in pms)
    )
    prompt = load_prompt("anniversary_security")
    tools, tool_choice = tool_params_for(AnniversaryRetro)
    return {
        "custom_id": f"security-{day_n}",
        "params": {
            "model": MODEL,
            "max_tokens": 2500,
            "system": [{"type": "text", "text": prompt,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": facts},
                {"type": "text",
                 "text": f"Produce the Day-{day_n} security retro."},
            ]}],
            "tools": tools,
            "tool_choice": tool_choice,
        },
    }


def _render(retro: AnniversaryRetro) -> str:
    lines = [f"# Day-{retro.day_n} security retro", "",
             retro.summary, ""]
    for label, items in (
        ("What you built", retro.what_you_built),
        ("What you learned", retro.what_you_learned),
        ("What drifted", retro.what_drifted),
        ("Next 30 days", retro.next_30_days),
    ):
        if items:
            lines.append(f"## {label}")
            for x in items:
                lines.append(f"- {x}")
            lines.append("")
    return "\n".join(lines)
