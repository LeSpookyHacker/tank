"""Meeting-prep brief generator.

Input: who you're meeting (person/team name or entity_id).
Output: a structured brief — their world, where you overlap, what you
don't know, ranked questions, one thing to offer.

Two execution paths:

- `prepare(...)` — synchronous, returns a dict. Used by
  `POST /api/meeting-prep` where the caller is waiting.
- `schedule_batch(meetings)` + `@batches.register("auto_brief")` —
  scheduler's nightly fan-out. Submits one batch to Anthropic's
  Batches API (50% off), persists each rehydrated brief into
  `meeting_briefs` when the result lands.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.claude import batches
from app.claude.batch_helpers import extract_validated, tool_params_for
from app.claude.caching import CACHE_5M, build_scope_block
from app.config import HAIKU_MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import find_by_name, get_card
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import MeetingPrepBrief
from app.storage import meeting_briefs_store

log = logging.getLogger("tank.meeting_prep")

_PH_RE = re.compile(
    r"\[(?:EMAIL|INTERNAL_HOST|HOST|PRIVATE_IP|PUBLIC_IP|"
    r"AWS_ACCT|AWS_ARN|GCP_PROJECT|AZURE_SUB|SECRET|PERSON|CUSTOM[A-Z_]*)_\d+\]"
)


def _ph_in(text: str) -> set[str]:
    return set(_PH_RE.findall(text or ""))


def _user_task_for(who: str, when: str | None,
                   extras: str | None) -> str:
    """Build the redacted user-task block from who/when/extras.

    Shared by the sync `prepare()` and the batched `_request_for()` so
    both paths send the same prompt shape — important for prompt-cache
    reuse across the two paths and for parity in output quality.
    """
    person = find_by_name("Person", who)
    person_id = person["id"] if person else None
    redacted_who = apply_redactions(who).redacted_text
    parts = [f"I'm meeting with {redacted_who}."]
    if when:
        parts.append(f"Time: {apply_redactions(when).redacted_text}.")
    if extras:
        parts.append(f"Context: {apply_redactions(extras).redacted_text}")
    if person_id:
        card = get_card(person_id)
        parts.append(f"Entity card for {redacted_who}: {card!r}")
    return "\n".join(parts)


def _rehydrate_brief(parsed: MeetingPrepBrief) -> dict:
    """Rehydrate every text field on a parsed brief. Pure dict out."""
    # Collect all text fields to find which placeholders actually appear.
    all_text = " ".join([
        parsed.who_summary or "",
        parsed.their_world or "",
        parsed.overlap or "",
        " ".join(parsed.unknowns or []),
        " ".join(
            (q.get("question", "") or "") + " " + (q.get("why", "") or "")
            for q in (parsed.ranked_questions or [])
        ),
        parsed.one_thing_to_offer or "",
    ])
    mapping = load_rehydration_map(_ph_in(all_text))

    def _rh(s: str) -> str:
        return rehydrate(s or "", mapping)

    return {
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


def prepare(*, who: str, when: str | None = None,
            extras: str | None = None) -> dict:
    """Return a rendered brief + raw structured form."""
    user_task = _user_task_for(who, when, extras)
    client = get_client()
    try:
        resp = client.messages.parse(
            model=HAIKU_MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": load_prompt("meeting_prep"),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    {**build_scope_block(), "cache_control": CACHE_5M},
                    {"type": "text", "text": user_task},
                ],
            }],
            output_format=MeetingPrepBrief,
        )
        log_token_usage("meeting_prep.prepare", HAIKU_MODEL, getattr(resp, "usage", None))
        parsed = getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.exception("meeting prep failed")
        return {"error": "Meeting prep failed. Please try again."}

    if parsed is None:
        return {"error": "no structured output returned"}

    return _rehydrate_brief(parsed)


# ── Batch path ─────────────────────────────────────────────────────────

def _request_for(meeting: dict) -> dict | None:
    """Build a single batch request dict for one meeting.

    Mirrors `prepare()`'s prompt + scope + user-task layout so cached
    blocks shared across sync and batch paths hit the same cache entry.
    Returns None if the meeting has no attendees (nothing to brief on).
    """
    attendees = meeting.get("attendees") or []
    if not attendees:
        return None
    who = attendees[0]
    user_task = _user_task_for(who, meeting.get("title"), None)
    tools, tool_choice = tool_params_for(MeetingPrepBrief)
    return {
        "custom_id": meeting["id"],
        "params": {
            "model": HAIKU_MODEL,
            "max_tokens": 4096,
            "system": [{
                "type": "text",
                "text": load_prompt("meeting_prep"),
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": [{
                "role": "user",
                "content": [
                    {**build_scope_block(), "cache_control": CACHE_5M},
                    {"type": "text", "text": user_task},
                ],
            }],
            "tools": tools,
            "tool_choice": tool_choice,
        },
    }


def schedule_batch(meetings: list[dict]) -> str | None:
    """Submit one batch covering N upcoming meetings.

    Caller is the scheduler's `_fire_auto_briefs`. Returns the tank-side
    batch_jobs row id, or None if every meeting was skipped (no attendees)
    or the batch submission failed.
    """
    requests = []
    meeting_id_by_custom = {}
    for m in meetings:
        req = _request_for(m)
        if req is None:
            continue
        requests.append(req)
        meeting_id_by_custom[req["custom_id"]] = m["id"]
    if not requests:
        return None
    return batches.submit(
        kind="auto_brief",
        requests=requests,
        payload={"meeting_id_by_custom": meeting_id_by_custom},
    )


@batches.register("auto_brief")
def _handle_auto_brief(custom_id: str, msg, payload: dict) -> None:
    """Per-result handler: rehydrate the brief and persist it."""
    parsed = extract_validated(msg, MeetingPrepBrief)
    if parsed is None:
        log.warning("auto_brief %s: no structured output", custom_id)
        return
    brief = _rehydrate_brief(parsed)
    meeting_id = (payload.get("meeting_id_by_custom") or {}).get(
        custom_id, custom_id,
    )
    meeting_briefs_store.insert(meeting_id=meeting_id, brief=brief)
