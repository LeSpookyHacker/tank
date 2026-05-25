"""Meeting-prep brief generator.

Input: who you're meeting (person/team name or entity_id).
Output: a structured brief — their world, where you overlap, what you
don't know, ranked questions, one thing to offer.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.claude.reports import _build_scope_block
from app.config import HAIKU_MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import find_by_name, get_card
from app.redact.engine import rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import MeetingPrepBrief

log = logging.getLogger("tank.meeting_prep")


def prepare(*, who: str, when: str | None = None,
            extras: str | None = None) -> dict:
    """Return a rendered brief + raw structured form."""
    person = find_by_name("Person", who)
    person_id = person["id"] if person else None

    user_task_parts = [f"I'm meeting with {who}."]
    if when:
        user_task_parts.append(f"Time: {when}.")
    if extras:
        user_task_parts.append(f"Context: {extras}")
    if person_id:
        card = get_card(person_id)
        user_task_parts.append(
            f"Entity card for {who}: {card!r}"
        )
    user_task = "\n".join(user_task_parts)

    client = get_client()
    try:
        resp = client.messages.parse(
            model=HAIKU_MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": load_prompt("meeting_prep"),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    _build_scope_block(),
                    {"type": "text", "text": user_task},
                ],
            }],
            output_format=MeetingPrepBrief,
        )
        log_token_usage("meeting_prep.prepare", HAIKU_MODEL, getattr(resp, "usage", None))
        parsed = getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.exception("meeting prep failed")
        return {"error": str(exc)}

    if parsed is None:
        return {"error": "no structured output returned"}

    # Rehydrate every text field.
    mapping = load_rehydration_map()
    def _rh(s: str) -> str:
        return rehydrate(s or "", mapping)

    rendered = {
        "who_summary": _rh(parsed.who_summary),
        "their_world": _rh(parsed.their_world),
        "overlap": _rh(parsed.overlap),
        "unknowns": [_rh(u) for u in parsed.unknowns],
        "ranked_questions": [
            {"question": _rh(q.get("question", "")),
             "why": _rh(q.get("why", ""))}
            for q in parsed.ranked_questions
        ],
        "one_thing_to_offer": _rh(parsed.one_thing_to_offer),
        "citations": parsed.citations,
    }
    return rendered
