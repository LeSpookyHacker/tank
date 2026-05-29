"""Design review intake + checklist scaffolding.

Flow:
1. User freewrites the design they're proposing.
2. `seed_intake(title, freewrite)` calls Sonnet with the intake prompt
   → returns `DesignReviewIntakePayload` (scope summary, likely risk
   areas, missing info, suggested reviewers, default checklist).
3. The user edits the proposal + checks off checklist items in the UI.
4. On approval, any "decisions made" entries are inserted into the
   `decisions` table with `source='design_review'`.
"""
from __future__ import annotations

import json
import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import find_by_name
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import DesignReviewChecklistItem, DesignReviewIntakePayload
from app.storage import design_reviews_store

log = logging.getLogger("tank.design_review")


_DEFAULT_CHECKLIST: list[dict] = [
    {"item": "AuthN: identity established for every caller",
     "category": "authn", "checked": False},
    {"item": "AuthZ: least-privilege scoped to caller",
     "category": "authz", "checked": False},
    {"item": "Data classification reviewed (PII, secrets, financials)",
     "category": "data", "checked": False},
    {"item": "Crypto: TLS in flight, encryption at rest, key custody",
     "category": "crypto", "checked": False},
    {"item": "Third-party deps: license, vuln history, supply-chain",
     "category": "deps", "checked": False},
    {"item": "Blast radius: what happens if this component is owned?",
     "category": "blast", "checked": False},
    {"item": "Logging & audit: who knows what happened, when?",
     "category": "logging", "checked": False},
    {"item": "Threat model touch-points (which existing TMs change?)",
     "category": "tm", "checked": False},
    {"item": "Rollout plan + rollback path",
     "category": "rollout", "checked": False},
    {"item": "IR runbook impact: detection + response known?",
     "category": "logging", "checked": False},
]


def seed_intake(*, title: str, freewrite: str,
                requester: str | None = None) -> str:
    """Create a design_review row and seed the checklist via Sonnet."""
    redacted = apply_redactions(freewrite).redacted_text
    payload = _generate_intake(title, redacted)

    checklist = ([c.model_dump() for c in payload.checklist]
                 if payload and payload.checklist
                 else list(_DEFAULT_CHECKLIST))

    body_red = (
        f"# {payload.title if payload else title}\n\n"
        f"## Scope\n{payload.scope_summary if payload else '—'}\n\n"
        f"## Likely risk areas\n"
        + "\n".join(f"- {x}" for x in (payload.likely_risk_areas if payload else []))
        + "\n\n## Missing info\n"
        + "\n".join(f"- {x}" for x in (payload.missing_info if payload else []))
        + "\n\n## Proposal (verbatim)\n"
        + redacted
    )
    body_md = rehydrate(body_red, load_rehydration_map())

    # resolve suggested reviewer names to entity IDs where possible
    scope_ids: list[str] = []
    if payload:
        for name in payload.suggested_reviewers:
            card = find_by_name("Person", name) or find_by_name("Service", name)
            if card:
                scope_ids.append(card["id"])

    dr_id = design_reviews_store.create(
        title=payload.title if payload else title,
        body_md=body_md, body_md_redacted=body_red,
        requester=requester, scope_entity_ids=scope_ids,
        checklist=checklist,
    )
    return dr_id


def _generate_intake(title: str, redacted_freewrite: str
                     ) -> DesignReviewIntakePayload | None:
    client = get_client()
    try:
        prompt = load_prompt("design_review_intake")
    except FileNotFoundError:
        log.warning("design_review_intake prompt missing")
        return None
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=3072,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": [
                           {"type": "text",
                            "text": f"# {apply_redactions(title).redacted_text}"},
                           {"type": "text", "text": redacted_freewrite},
                           {"type": "text",
                            "text": "Produce the structured intake."},
                       ]}],
            output_format=DesignReviewIntakePayload,
        )
        log_token_usage("design_review.intake", MODEL, getattr(resp, "usage", None))
        return getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("design_review intake LLM failed: %s", exc)
        return None
