"""Light-touch journal-entry extraction.

The user dumps a one-line "what happened today" entry. We parse it
for any entities/edges/follow-ups worth surfacing — cheap prompt, no
expensive structured output.

If the entry has any extractable items, we attach them to the journal
row and the nudge generator may pick one up as a follow-up suggestion.
"""
from __future__ import annotations

import logging

from app.config import MODEL, get_client, load_prompt
from app.redact.engine import apply_redactions
from app.schemas import NotesDiff
from app.storage import journal_store

log = logging.getLogger("tank.journal_extractor")


def submit(body: str) -> dict:
    """Persist today's journal entry; extract any follow-ups."""
    redacted = apply_redactions(body)
    journal_id = journal_store.upsert_for_today(
        body=body, body_redacted=redacted.redacted_text,
    )
    diff = _extract(redacted.redacted_text)
    journal_store.set_extracted(
        journal_id,
        diff.model_dump() if hasattr(diff, "model_dump") else diff,
    )
    return {"journal_id": journal_id,
            "diff": diff.model_dump()
            if hasattr(diff, "model_dump") else diff}


def _extract(body_redacted: str) -> NotesDiff:
    client = get_client()
    try:
        prompt = load_prompt("journal_extractor")
    except FileNotFoundError:
        prompt = ("Extract any follow-ups, entities, or facts from "
                  "the user's daily journal entry. Be conservative.")
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=1024,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": "Journal:\n\n" + body_redacted}],
            output_format=NotesDiff,
        )
        parsed = getattr(resp, "parsed_output", None)
        return parsed if parsed is not None else NotesDiff()
    except Exception as exc:
        log.warning("journal extraction failed: %s", exc)
        return NotesDiff()
