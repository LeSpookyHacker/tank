"""Glossary candidate extraction.

Run periodically (or after a batch ingest) to surface company jargon
the user should define. Sonnet sees a sample of redacted chunks and
returns terms it doesn't recognize as standard English / standard
infosec vocabulary.

User confirms in `/glossary` — confirmed terms then enrich chat
context (the cached KB block can include the glossary).
"""
from __future__ import annotations

import logging

from app.config import MODEL, get_client, load_prompt
from app.kb.search import hybrid_search
from app.schemas import GlossaryExtraction
from app.storage import glossary_store

log = logging.getLogger("tank.glossary")


def discover(sample_size: int = 30) -> list[str]:
    """Look at a sample of recent chunks, propose glossary terms.

    Returns the IDs of newly-inserted (pending) glossary entries.
    Existing terms get their `occurrences` bumped.
    """
    # Use a hybrid search for generic infra terms to grab representative
    # chunks. (Replace with a more targeted sampler later.)
    sample_queries = [
        "service architecture", "authentication", "deployment",
        "data flow", "internal team",
    ]
    samples: list[str] = []
    for q in sample_queries:
        hits = hybrid_search(q, k=6)
        for h in hits:
            samples.append(h.snippet or "")
    body = "\n\n".join(samples[:sample_size])
    if not body.strip():
        return []

    client = get_client()
    try:
        prompt = load_prompt("glossary_extract")
    except FileNotFoundError:
        log.warning("glossary_extract prompt missing")
        return []
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "## Sample chunks\n" + body},
                {"type": "text", "text": "Propose glossary entries."},
            ]}],
            output_format=GlossaryExtraction,
        )
        parsed = getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("glossary discover failed: %s", exc)
        return []
    if not parsed:
        return []

    ids = []
    for c in parsed.candidates:
        gid = glossary_store.upsert(
            term=c.term, definition=c.definition,
            aliases=c.aliases, confirmed=False,
        )
        ids.append(gid)
    return ids
