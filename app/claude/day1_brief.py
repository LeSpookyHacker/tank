"""Day-1 brief generator.

At the end of conversational onboarding, generate a one-page
printable artifact: scope echo, top 5 entities, week-1 questions,
week-1 reading, week-1 meetings. Stored as a Report
(`kind='day1_brief'`) so it lives next to the other generated docs.
"""
from __future__ import annotations

import logging

from app.claude.reports import _build_scope_block, _finalize
from app.config import MODEL, get_client, load_prompt
from app.redact.engine import rehydrate
from app.redact.store import load_rehydration_map
from app.role import get_state
from app.schemas import Day1Brief

log = logging.getLogger("tank.day1")


def generate() -> str:
    state = get_state()
    scope = state.user_scope.model_dump() if state.user_scope else {}
    user_task = (
        f"User's scope: {scope}\n\n"
        "Generate a Day-1 brief. Keep it actionable, tight, and "
        "honest about what we don't know yet."
    )
    client = get_client()
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": load_prompt("day1_brief"),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    _build_scope_block(),
                    {"type": "text", "text": user_task},
                ],
            }],
            output_format=Day1Brief,
        )
        parsed = getattr(resp, "parsed_output", None)
        usage = getattr(resp, "usage", None)
    except Exception as exc:
        log.exception("day1 brief failed")
        raise

    if parsed is None:
        raise RuntimeError("day1 brief returned no structured output")

    md = _render_day1(parsed)
    usage_d = {}
    if usage:
        usage_d = {
            "tokens_in": getattr(usage, "input_tokens", 0) or 0,
            "tokens_out": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_in": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_create_in": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        }
    return _finalize(
        kind="day1_brief",
        title="Day-1 brief",
        content_md_redacted=md,
        usage=usage_d,
    )


def _render_day1(brief: Day1Brief) -> str:
    lines = ["# Day 1 brief", "", "## Your scope (as I understood it)", "",
             brief.scope_echo, ""]

    if brief.top_entities:
        lines.append("## Top 5 entities you should know")
        lines.append("")
        for e in brief.top_entities[:5]:
            name = e.get("name", "?")
            t = e.get("type", "?")
            one_line = e.get("one_line", "")
            lines.append(f"- **{name}** _{t}_ — {one_line}")
        lines.append("")

    if brief.week1_questions:
        lines.append("## 3 questions to ask in week 1")
        lines.append("")
        for q in brief.week1_questions[:3]:
            lines.append(f"### Ask {q.who_to_ask}: _{q.question}_")
            lines.append(q.why_it_matters)
            lines.append("")

    if brief.week1_reading:
        lines.append("## 3 things to read first")
        lines.append("")
        for r in brief.week1_reading[:3]:
            lines.append(f"- **{r.title}** — {r.why}")
        lines.append("")

    if brief.week1_meetings:
        lines.append("## 3 meetings to set up this week")
        lines.append("")
        for m in brief.week1_meetings[:3]:
            when = f" ({m.suggested_when})" if m.suggested_when else ""
            lines.append(f"- **{m.who}**{when} — {m.why}")
        lines.append("")

    return "\n".join(lines)
