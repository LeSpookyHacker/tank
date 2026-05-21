"""Anniversary retrospective generator.

Fires at Day 30/60/90/180/365 (scheduler-driven). Produces a
retrospective report that walks the entity-graph + chat-history
windows ending on the anniversary and surfaces what changed.
"""
from __future__ import annotations

import logging

from app.claude.reports import _build_scope_block, _finalize
from app.config import MODEL, get_client, load_prompt
from app.role import get_state, tenure_day
from app.schemas import AnniversaryRetro

log = logging.getLogger("tank.anniversary")


def generate(day_n: int) -> str:
    """Generate the Day-`day_n` retrospective."""
    state = get_state()
    scope = state.user_scope.model_dump() if state.user_scope else {}
    user_task = (
        f"User's scope: {scope}\n"
        f"Days into tenure: {day_n}\n\n"
        "Produce a retrospective: what was built, what was learned, "
        "what's drifted since onboarding, what to prioritize over the "
        f"next 30 days."
    )
    client = get_client()
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": load_prompt("anniversary"),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    _build_scope_block(),
                    {"type": "text", "text": user_task},
                ],
            }],
            output_format=AnniversaryRetro,
        )
        parsed = getattr(resp, "parsed_output", None)
        usage = getattr(resp, "usage", None)
    except Exception as exc:
        log.exception("anniversary retro day %d failed", day_n)
        raise

    if parsed is None:
        raise RuntimeError("anniversary retro returned no structured output")

    md = _render_retro(parsed)
    usage_d = {}
    if usage:
        usage_d = {
            "tokens_in": getattr(usage, "input_tokens", 0) or 0,
            "tokens_out": getattr(usage, "output_tokens", 0) or 0,
        }
    return _finalize(
        kind=f"anniversary_{day_n}",
        title=f"Day-{day_n} retrospective",
        content_md_redacted=md,
        usage=usage_d,
        scope={"day_n": day_n},
    )


def _render_retro(r: AnniversaryRetro) -> str:
    lines = [f"# Day-{r.day_n} retrospective", "", r.summary, ""]

    if r.what_you_built:
        lines.append("## What you built")
        for x in r.what_you_built:
            lines.append(f"- {x}")
        lines.append("")

    if r.what_you_learned:
        lines.append("## What you learned")
        for x in r.what_you_learned:
            lines.append(f"- {x}")
        lines.append("")

    if r.what_drifted:
        lines.append("## What drifted")
        for x in r.what_drifted:
            lines.append(f"- {x}")
        lines.append("")

    if r.next_30_days:
        lines.append("## Next 30 days")
        for x in r.next_30_days:
            lines.append(f"- {x}")
        lines.append("")

    return "\n".join(lines)
