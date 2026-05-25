"""Entity + relationship extraction via Claude messages.parse.

Two entry points:
- extract_entities_for_doc(doc_id, chunks, chunk_ids, ...): batches the
  doc's chunks into Claude calls, persists entities + relationships +
  entity↔chunk links.
- extract_from_diagram(b64, media_type): vision-based extraction for
  architecture diagrams.

We call Claude in small batches (a few chunks per call) rather than
one chunk at a time, to amortize the cost and let the model see
multiple-chunk context for cross-chunk entities.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Iterable

from app.config import HAIKU_MODEL, MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions
from app.schemas import ChunkExtraction, DiagramExtraction
from app.storage import entities_store, relationships_store

log = logging.getLogger("tank.extractor")

# How many chunks per Claude call. Picking 4 keeps a single call under
# ~6k input tokens (4 chunks × ~800 tokens + prompt + schema).
_BATCH_SIZE = 4

# Limit concurrent extraction calls so bulk folder ingests don't blow the
# rate limit. Two slots means at most 2 Claude calls in flight at once
# across all background ingest tasks.
_SEM = threading.Semaphore(2)

# Seconds to wait before each retry attempt (1st through 5th).
_RETRY_DELAYS = [5, 15, 30, 60, 120]


def _system_prompt() -> dict:
    """Cached system block — same across every extraction call."""
    return {
        "type": "text",
        "text": load_prompt("extract_entities"),
        "cache_control": {"type": "ephemeral"},
    }


def _format_batch(batch_chunks: list[dict], batch_ids: list[str]) -> str:
    parts = []
    for chunk_id, c in zip(batch_ids, batch_chunks):
        section = c.get("section_path") or "—"
        parts.append(
            f"<chunk id={chunk_id} section={section!r}>\n"
            f"{c['text_redacted']}\n"
            f"</chunk>"
        )
    return "\n\n".join(parts)


def _safe_parse(api_resp) -> ChunkExtraction:
    """Pull a ChunkExtraction out of a messages.parse response."""
    parsed = getattr(api_resp, "parsed_output", None)
    if parsed is not None:
        return parsed
    # Fallback: walk the content blocks looking for JSON.
    for block in getattr(api_resp, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                obj = json.loads(text)
                return ChunkExtraction(**obj)
            except Exception:
                continue
    return ChunkExtraction()


def _call_claude(batch_text: str) -> ChunkExtraction:
    client = get_client()
    with _SEM:
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                resp = client.messages.parse(
                    model=HAIKU_MODEL,
                    max_tokens=4096,
                    system=[_system_prompt()],
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text",
                             "text": "Extract entities and relationships from "
                                     "these redacted chunks. Return JSON only.\n\n"
                                     + batch_text},
                        ],
                    }],
                    output_format=ChunkExtraction,
                )
                log_token_usage("extractor.batch", HAIKU_MODEL, getattr(resp, "usage", None))
                return _safe_parse(resp)
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "rate_limit" in str(exc)
                if is_rate_limit and attempt < len(_RETRY_DELAYS):
                    delay = _RETRY_DELAYS[attempt]
                    log.warning("extractor 429 — waiting %ds before retry %d/%d",
                                delay, attempt + 1, len(_RETRY_DELAYS))
                    time.sleep(delay)
                    continue
                log.warning("extractor batch failed: %s", exc)
                return ChunkExtraction()
    return ChunkExtraction()


def extract_entities_for_doc(doc_id: str, chunks: list[dict],
                             chunk_ids: list[str], *,
                             kind: str = "default",
                             parsed_meta: dict | None = None) -> None:
    """Run extraction over a document's chunks and persist results.

    For 'image' kind, the parser already produced structured extraction
    in `parsed_meta['vision']`; we skip the LLM call and persist that.
    """
    if kind == "image" and parsed_meta and parsed_meta.get("vision"):
        _persist_from_dict(doc_id, chunk_ids[0] if chunk_ids else None,
                           parsed_meta["vision"])
        return

    for start in range(0, len(chunks), _BATCH_SIZE):
        batch_chunks = chunks[start:start + _BATCH_SIZE]
        batch_ids = chunk_ids[start:start + _BATCH_SIZE]
        batch_text = _format_batch(batch_chunks, batch_ids)
        extraction = _call_claude(batch_text)
        _persist(doc_id, batch_ids, extraction)


def _persist(doc_id: str, batch_chunk_ids: list[str],
             extraction: ChunkExtraction) -> None:
    name_to_id: dict[tuple[str, str], str] = {}
    for ent in extraction.entities:
        eid = entities_store.upsert_entity(
            type_=ent.type,
            name=ent.name,
            description=ent.description,
            attrs=ent.attrs,
            confidence=ent.confidence,
            provenance="inferred",
            first_seen_doc=doc_id,
        )
        name_to_id[(ent.type, ent.name.lower().strip())] = eid
        # Link to every chunk in the batch — coarse but cheap;
        # citation rendering pulls the highest-relevance chunk anyway.
        for cid in batch_chunk_ids:
            entities_store.link_chunk(eid, cid)

    for edge in extraction.relationships:
        # Make sure both endpoints exist (auto-create stubs).
        src_id = name_to_id.get((edge.src_type, edge.src_name.lower().strip()))
        if src_id is None:
            src_id = entities_store.upsert_entity(
                type_=edge.src_type, name=edge.src_name,
                provenance="inferred", first_seen_doc=doc_id,
                confidence=edge.confidence * 0.5,
            )
            name_to_id[(edge.src_type, edge.src_name.lower().strip())] = src_id
        dst_id = name_to_id.get((edge.dst_type, edge.dst_name.lower().strip()))
        if dst_id is None:
            dst_id = entities_store.upsert_entity(
                type_=edge.dst_type, name=edge.dst_name,
                provenance="inferred", first_seen_doc=doc_id,
                confidence=edge.confidence * 0.5,
            )
            name_to_id[(edge.dst_type, edge.dst_name.lower().strip())] = dst_id
        relationships_store.upsert_relationship(
            src_id=src_id, dst_id=dst_id, kind=edge.kind,
            attrs=edge.attrs, confidence=edge.confidence,
            provenance="inferred", first_seen_doc=doc_id,
        )


def _persist_from_dict(doc_id: str, anchor_chunk_id: str | None,
                       d: dict) -> None:
    """Persist a vision extraction returned as a dict (skips LLM call)."""
    try:
        extraction = ChunkExtraction(**{
            "entities": d.get("entities", []),
            "relationships": d.get("relationships", []),
        })
    except Exception as exc:
        log.warning("vision extraction malformed: %s", exc)
        return
    _persist(doc_id, [anchor_chunk_id] if anchor_chunk_id else [], extraction)


# ---------------- vision (called by image parser) ----------------

def extract_from_diagram(b64: str, media_type: str) -> dict:
    """Call Sonnet 4.6 vision with the diagram. Returns a plain dict
    (not a Pydantic model) so the parser can stash it in `meta`.
    """
    client = get_client()
    prompt_text = load_prompt("extract_arch_diagram")
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": prompt_text,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64",
                                "media_type": media_type, "data": b64}},
                    {"type": "text",
                     "text": "Extract the architecture entities and "
                             "relationships from this diagram. Return JSON only."},
                ],
            }],
            output_format=DiagramExtraction,
        )
        log_token_usage("extractor.vision", MODEL, getattr(resp, "usage", None))
        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            return {"entities": [], "relationships": [],
                    "diagram_summary": ""}
        # Redact extracted names before returning — vision sometimes
        # surfaces internal hostnames the redactor wouldn't see in text.
        out: dict = {
            "diagram_summary": apply_redactions(parsed.diagram_summary or "").redacted_text,
            "entities": [],
            "relationships": [],
        }
        for e in parsed.entities:
            out["entities"].append({
                "type": e.type,
                "name": apply_redactions(e.name).redacted_text,
                "description": apply_redactions(e.description or "").redacted_text or None,
                "attrs": e.attrs,
                "confidence": e.confidence,
            })
        for r in parsed.relationships:
            out["relationships"].append({
                "src_type": r.src_type,
                "src_name": apply_redactions(r.src_name).redacted_text,
                "dst_type": r.dst_type,
                "dst_name": apply_redactions(r.dst_name).redacted_text,
                "kind": r.kind,
                "attrs": r.attrs,
                "confidence": r.confidence,
            })
        return out
    except Exception as exc:
        log.warning("vision extraction failed: %s", exc)
        return {"entities": [], "relationships": [], "diagram_summary": ""}
