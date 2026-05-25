# caching.py — Build cacheable prompt blocks for chat + reports.
# Phase 6 (tankinstuction): build_system_block() now accepts project_notes;
# appended only for project-scoped chat (never for the global side-panel).
#
# Two breakpoints per request:
# 1. End of system prompt (stable per role × lens × project notes).
# 2. End of KB context block (the retrieved chunks + entity cards).
from __future__ import annotations

from app.config import load_prompt


def build_system_block(
    role_mode: str,
    lens: str | None = None,
    project_notes: str = "",
) -> dict:
    """Return one cache-controlled text block for the system prompt.

    role_mode ∈ {ic, manager, both}. lens ∈ {map, prioritize, execute,
    maintain, None} (None = pre-onboarding).
    project_notes: non-empty only for project-scoped chat sessions.
    """
    base = load_prompt(f"chat_system_{role_mode}")
    lens_text = ""
    if lens:
        try:
            lens_text = "\n\n## Current lens: " + lens.upper() + "\n\n" + \
                        load_prompt(f"chat_lens_{lens}")
        except FileNotFoundError:
            lens_text = ""
    notes_text = ""
    if project_notes and project_notes.strip():
        notes_text = "\n\n## Project Context\n\n" + project_notes.strip()
    return {
        "type": "text",
        "text": base + lens_text + notes_text,
        "cache_control": {"type": "ephemeral"},
    }


def build_kb_block(hits: list[dict], entity_cards: list[dict]) -> dict:
    """Format retrieved context as ONE cache-controlled text block.

    Layout:

      ## KB context
      ### Top chunks (N)
      [chunk_id=...] (document_id=..., section=...)
      <snippet>

      ### Entity cards (N)
      [entity_id=...] type=Service name=...
      description: ...
      attrs: {...}
      edges: N
    """
    parts: list[str] = ["## KB context"]
    if hits:
        parts.append(f"### Top chunks ({len(hits)})")
        for h in hits:
            parts.append(
                f"[chunk_id={h['chunk_id']}] "
                f"(document_id={h['document_id']}, "
                f"section={h.get('section_path') or '—'})"
            )
            parts.append(h.get("snippet", "") or "")
            parts.append("")
    if entity_cards:
        parts.append(f"### Entity cards ({len(entity_cards)})")
        for c in entity_cards:
            parts.append(
                f"[entity_id={c['id']}] type={c['type']} name={c['name']!r} "
                f"provenance={c['provenance']} confidence={c['confidence']:.2f}"
            )
            if c.get("description"):
                parts.append(f"description: {c['description']}")
            if c.get("attrs"):
                parts.append(f"attrs: {c['attrs']}")
            parts.append(f"edges: {c.get('edges_count', 0)}")
            parts.append("")

    text = "\n".join(parts) if (hits or entity_cards) else \
        "## KB context\n(no relevant chunks found)"
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }
