"""Extract decisions from ingested documents.

Postmortems, design docs, and ADRs ("we decided to…", "we accepted…",
"we deferred…") contain implicit decisions. This module runs Sonnet
over a document's chunks and proposes a `DecisionExtraction` payload
the user confirms via the notes-style diff UI before committing into
the `decisions` table.

Auto-runs on ingest only for category='people_process' docs whose
title or path matches /postmortem|adr|design/i — those are the
high-signal targets. Architecture docs can be opted in manually.
"""
from __future__ import annotations

import json
import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import find_by_name
from app.redact.engine import apply_redactions
from app.schemas import DecisionExtraction
from app.storage import decisions_store
from app.storage.chunks_store import list_chunks_for_doc
from app.storage.documents_store import get_document

log = logging.getLogger("tank.decisions")


def extract_from_doc(doc_id: str) -> DecisionExtraction | None:
    """Run extraction over a document's chunks. Returns the payload
    without committing — caller commits via `commit_extraction()`.
    """
    doc = get_document(doc_id)
    if not doc:
        return None
    chunks = list_chunks_for_doc(doc_id)
    if not chunks:
        return None

    body = "\n\n".join(
        f"chunk[{c['id']}] section={c.get('section_path') or '—'}:\n"
        f"{c['text_redacted']}"
        for c in chunks[:30]
    )

    client = get_client()
    try:
        prompt = load_prompt("extract_decisions")
    except FileNotFoundError:
        log.warning("extract_decisions prompt missing")
        return None

    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": [
                           {"type": "text",
                            "text": f"## Document: {apply_redactions(doc.get('title') or doc['source_path']).redacted_text}"},
                           {"type": "text", "text": body},
                           {"type": "text",
                            "text": "Extract any deliberate decisions, "
                                    "accepted risks, deferred fixes, or "
                                    "security invariants stated in this "
                                    "document. Return the structured "
                                    "DecisionExtraction."},
                       ]}],
            output_format=DecisionExtraction,
        )
        log_token_usage("decisions.extract", MODEL, getattr(resp, "usage", None))
        return getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("extract_decisions failed for doc %s: %s", doc_id, exc)
        return None


def commit_extraction(doc_id: str, payload: DecisionExtraction,
                      accept_indices: list[int] | None = None) -> list[str]:
    """Commit a subset (or all) of the extracted decisions to the DB.

    Returns the created decision IDs.
    """
    created: list[str] = []
    selected = (
        payload.decisions if accept_indices is None
        else [d for i, d in enumerate(payload.decisions) if i in accept_indices]
    )
    for ed in selected:
        scope_ids: list[str] = []
        for name in ed.suggested_scope_entity_names:
            card = find_by_name("Service", name)
            if card:
                scope_ids.append(card["id"])
        expires_at = None
        if ed.suggested_expires_days:
            import time
            expires_at = time.time() + ed.suggested_expires_days * 86400
        did = decisions_store.create(
            title=ed.title,
            body_md=ed.body,
            body_md_redacted=ed.body,
            kind=ed.kind if ed.kind in
                {"design_choice", "accepted_risk",
                 "deferred_fix", "security_invariant"}
                else "design_choice",
            scope_entity_ids=scope_ids,
            rationale=ed.rationale,
            expires_at=expires_at,
            source="extracted",
            source_doc_id=doc_id,
        )
        created.append(did)
    return created
