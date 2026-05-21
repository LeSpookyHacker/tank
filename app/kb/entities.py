"""Entity card builder + lookup helpers used by chat tools + reports."""
from __future__ import annotations

import json

from app.storage import chunks_store, entities_store, relationships_store


def get_card(entity_id: str, *, linked_chunks_limit: int = 5) -> dict | None:
    ent = entities_store.get_entity(entity_id)
    if not ent:
        return None
    chunk_ids = entities_store.linked_chunks(entity_id,
                                             limit=linked_chunks_limit)
    chunks = chunks_store.chunks_for_ids(chunk_ids)
    out_chunks = [
        {
            "chunk_id": c["id"],
            "document_id": c["document_id"],
            "section_path": c["section_path"],
            "snippet": (c["text_redacted"] or "")[:300],
        }
        for c in chunks
    ]
    out_edges = relationships_store.list_for_entity(entity_id)
    return {
        "id": ent["id"],
        "type": ent["type"],
        "name": ent["name"],
        "description": ent["description"],
        "attrs": json.loads(ent["attrs_json"] or "{}"),
        "confidence": ent["confidence"],
        "provenance": ent["provenance"],
        "first_seen_doc": ent["first_seen_doc"],
        "linked_chunks": out_chunks,
        "edges_count": len(out_edges),
    }


def find_by_name(type_: str, name: str) -> dict | None:
    ent = entities_store.find_entity(type_, name)
    if not ent:
        return None
    return get_card(ent["id"])


def list_by_type(type_: str, *, limit: int = 100) -> list[dict]:
    rows = entities_store.list_entities(type_=type_, limit=limit)
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "name": r["name"],
            "description": r["description"],
            "confidence": r["confidence"],
            "provenance": r["provenance"],
        }
        for r in rows
    ]
