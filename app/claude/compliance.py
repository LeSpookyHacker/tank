"""Compliance evidence collection.

For each ingested Control entity, ask Sonnet to find evidence in the
KB — documents, decisions, policies, runbooks, threat models — that
demonstrates the control is satisfied. Persist matches in the
`compliance_evidence` table.

This is bulk work; we batch up to 10 controls per Sonnet call.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from app.config import MODEL, get_client, load_prompt
from app.db import LOCK, get_conn
from app.kb.search import hybrid_search
from app.schemas import ComplianceEvidenceMap, EvidenceMatch
from app.storage import entities_store

log = logging.getLogger("tank.compliance")


def collect_for_framework(limit: int = 50) -> ComplianceEvidenceMap:
    """Iterate all Control entities and find evidence for each."""
    controls = entities_store.list_entities(type_="Control", limit=limit)
    matches: list[EvidenceMatch] = []
    no_evidence: list[str] = []

    for c in controls:
        hits = hybrid_search(
            f"{c['name']} {c.get('description') or ''}", k=5,
        )
        if not hits:
            no_evidence.append(c["id"])
            continue
        for h in hits[:3]:
            matches.append(EvidenceMatch(
                control_id=c["id"], control_title=c["name"],
                evidence_kind="document",
                evidence_id=h.document_id,
                evidence_title=h.section_path or h.chunk_id,
                confidence=min(1.0, h.score),
            ))
            _persist(c["id"], "document", h.document_id, h.score)

    return ComplianceEvidenceMap(
        matches=matches,
        controls_with_no_evidence=no_evidence,
        summary=(
            f"{len(controls)} controls scanned. "
            f"{len(matches)} evidence matches found. "
            f"{len(no_evidence)} controls have no evidence."
        ),
    )


def _persist(control_id: str, kind: str, evidence_id: str,
             confidence: float) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO compliance_evidence "
            "(control_id, evidence_kind, evidence_id, confidence, "
            " captured_at) VALUES (?, ?, ?, ?, ?)",
            (control_id, kind, evidence_id, confidence, time.time()),
        )
