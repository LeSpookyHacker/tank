"""Extract lessons from artifacts.

Runs on:
- Postmortems on publish — pull lessons from contributing factors +
  what we learned sections.
- Design reviews on rejection — pull lessons from the rejection
  rationale.
- Tabletop captures — see `claude/tabletop.capture_lessons()` for the
  inline path.

Lessons go into `lessons` and surface in chat via `search_lessons()`.
"""
from __future__ import annotations

import json
import logging

from app.config import MODEL, get_client, load_prompt
from app.schemas import LessonExtraction
from app.storage import lessons_store

log = logging.getLogger("tank.lessons")


def extract_from_postmortem(pm_id: str, pm_body_redacted: str) -> list[str]:
    """Return the IDs of lessons created from this postmortem."""
    payload = _run(
        scope_label="postmortem",
        body=pm_body_redacted,
        instruction="Extract 1-4 lessons learned from this "
                    "postmortem. Focus on patterns that would apply "
                    "to other services.",
    )
    if not payload:
        return []
    ids = []
    for lesson in payload.lessons:
        lid = lessons_store.create(
            title=lesson.title, body_md=lesson.body_md,
            source_kind="postmortem", source_id=pm_id,
            tags=lesson.tags,
        )
        ids.append(lid)
    return ids


def extract_from_design_review(dr_id: str, body_redacted: str) -> list[str]:
    payload = _run(
        scope_label="design_review",
        body=body_redacted,
        instruction="Extract 1-3 lessons or principles from this "
                    "design review. Focus on what the team learned "
                    "about the design, not what they decided.",
    )
    if not payload:
        return []
    ids = []
    for lesson in payload.lessons:
        lid = lessons_store.create(
            title=lesson.title, body_md=lesson.body_md,
            source_kind="design_review", source_id=dr_id,
            tags=lesson.tags,
        )
        ids.append(lid)
    return ids


def _run(*, scope_label: str, body: str,
         instruction: str) -> LessonExtraction | None:
    client = get_client()
    try:
        prompt = load_prompt("lesson_extractor")
    except FileNotFoundError:
        log.warning("lesson_extractor prompt missing")
        return None
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "text", "text": f"## Source: {scope_label}"},
                {"type": "text", "text": body},
                {"type": "text", "text": instruction},
            ]}],
            output_format=LessonExtraction,
        )
        return getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("lesson extraction failed for %s: %s", scope_label, exc)
        return None
