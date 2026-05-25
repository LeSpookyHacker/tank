"""Learning-capture extraction + commit.

Flow:
1. User dumps freewrite text (`POST /api/notes`).
2. We redact + persist; call Claude to extract proposed entities/edges/facts.
3. Stash the diff in `notes.extracted_json` WITHOUT committing.
4. User reviews diff in UI; on confirm, we write accepted items to KB
   with `provenance='user'`.
"""
from __future__ import annotations

import json
import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions
from app.schemas import NotesDiff
from app.storage import (entities_store, notes_store,
                         relationships_store)

log = logging.getLogger("tank.notes")


def create_note(*, body: str,
                meeting_with_entity_id: str | None = None) -> dict:
    redacted = apply_redactions(body)
    note_id = notes_store.insert(
        body=body,
        body_redacted=redacted.redacted_text,
        meeting_with_entity_id=meeting_with_entity_id,
    )

    # Extract diff asynchronously-but-synchronously (caller is in a
    # background task or blocking endpoint — short enough either way).
    diff = _extract_diff(redacted.redacted_text, meeting_with_entity_id)
    notes_store.update_extracted(note_id, diff.model_dump()
                                 if hasattr(diff, "model_dump")
                                 else diff)
    return {"note_id": note_id, "diff": diff.model_dump()
            if hasattr(diff, "model_dump") else diff}


def _extract_diff(body_redacted: str,
                  meeting_with_entity_id: str | None) -> NotesDiff:
    client = get_client()
    try:
        prompt = load_prompt("notes_to_kb")
    except FileNotFoundError:
        prompt = ("Extract proposed entities, relationships, and facts "
                  "from the user's freewrite notes. Return JSON only.")
    user_text = "Notes:\n\n" + body_redacted
    if meeting_with_entity_id:
        user_text += f"\n\n(context: meeting with entity_id={meeting_with_entity_id})"
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
            output_format=NotesDiff,
        )
        log_token_usage("notes.extract", MODEL, getattr(resp, "usage", None))
        parsed = getattr(resp, "parsed_output", None)
        return parsed if parsed is not None else NotesDiff()
    except Exception as exc:
        log.warning("notes diff extraction failed: %s", exc)
        return NotesDiff()


def commit_diff(*, note_id: str, accept: dict) -> dict:
    """User-confirmed items get written to KB with provenance='user'.

    `accept` shape:
      {
        "entities": [<index into new_entities>, ...],
        "relationships": [<index>, ...],
      }
    """
    note = notes_store.get(note_id)
    if not note:
        return {"error": "no such note"}

    try:
        diff_raw = json.loads(note["extracted_json"] or "{}")
        diff = NotesDiff(**diff_raw)
    except Exception:
        return {"error": "extracted diff malformed"}

    name_to_id: dict[tuple[str, str], str] = {}
    written_entities = 0
    for idx in accept.get("entities", []):
        if idx >= len(diff.new_entities):
            continue
        e = diff.new_entities[idx]
        eid = entities_store.upsert_entity(
            type_=e.type, name=e.name, description=e.description,
            attrs=e.attrs, confidence=1.0, provenance="user",
        )
        name_to_id[(e.type, e.name.lower().strip())] = eid
        written_entities += 1

    written_edges = 0
    for idx in accept.get("relationships", []):
        if idx >= len(diff.new_relationships):
            continue
        r = diff.new_relationships[idx]
        src_id = name_to_id.get((r.src_type, r.src_name.lower().strip()))
        if src_id is None:
            src_id = entities_store.upsert_entity(
                type_=r.src_type, name=r.src_name,
                provenance="user", confidence=0.8,
            )
        dst_id = name_to_id.get((r.dst_type, r.dst_name.lower().strip()))
        if dst_id is None:
            dst_id = entities_store.upsert_entity(
                type_=r.dst_type, name=r.dst_name,
                provenance="user", confidence=0.8,
            )
        relationships_store.upsert_relationship(
            src_id=src_id, dst_id=dst_id, kind=r.kind,
            attrs=r.attrs, confidence=1.0, provenance="user",
        )
        written_edges += 1

    notes_store.mark_confirmed(note_id)
    return {
        "note_id": note_id,
        "written_entities": written_entities,
        "written_edges": written_edges,
    }
