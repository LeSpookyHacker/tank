"""Risk register — Claude-assisted assessment.

`assess(risk_id)` pulls KB context (controls, threat models, decisions) for
the services in scope, asks Sonnet to estimate residual risk given current
controls, and updates the risk row with the output.
"""
from __future__ import annotations

import logging
import time

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions
from app.schemas import RiskAssessmentOutput
from app.storage import risks_store

log = logging.getLogger("tank.risk_register")


def assess(risk_id: str) -> RiskAssessmentOutput | None:
    """Run Sonnet over KB context to estimate residual risk and recommend treatment.

    Updates the risk row in-place. Returns None on failure.
    """
    risk = risks_store.get(risk_id)
    if not risk:
        log.warning("assess: risk %s not found", risk_id)
        return None

    context_parts = _build_context(risk)
    task = (
        f"Risk title: {risk['title']}\n"
        f"Description: {risk['description']}\n"
        f"Category: {risk['category']}\n"
        f"Inherent likelihood (1-5): {risk['inherent_likelihood']}\n"
        f"Inherent impact (1-5): {risk['inherent_impact']}\n\n"
        "Review the KB context above and assess residual risk after existing controls. "
        "Recommend a treatment (mitigate / accept / transfer / avoid) with rationale."
    )

    client = get_client()
    try:
        prompt = load_prompt("risk_assessment")
    except FileNotFoundError:
        prompt = "You are a security risk assessor. Evaluate the risk using the KB context."

    system_block = {
        "type": "text", "text": prompt,
        "cache_control": {"type": "ephemeral"},
    }
    context_block = {
        "type": "text",
        "text": apply_redactions("\n\n".join(context_parts)).redacted_text,
        "cache_control": {"type": "ephemeral"},
    }

    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[system_block],
            messages=[{"role": "user", "content": [
                context_block,
                {"type": "text", "text": apply_redactions(task).redacted_text},
            ]}],
            output_format=RiskAssessmentOutput,
        )
        log_token_usage("risk_register.assess", MODEL, getattr(resp, "usage", None))
        result: RiskAssessmentOutput = resp.parsed_output

        # Compute 90-day review date from now.
        review_at = int(time.time()) + 90 * 86400

        treatment = apply_redactions(result.recommended_treatment or "").redacted_text
        rationale = apply_redactions(result.treatment_rationale or "").redacted_text

        risks_store.update_assessment(
            risk_id,
            residual_likelihood=result.residual_likelihood,
            residual_impact=result.residual_impact,
            treatment=treatment,
            treatment_rationale=rationale,
            review_at=review_at,
        )
        return result
    except Exception as exc:
        log.warning("risk assess %s failed: %s", risk_id, exc)
        return None


def _build_context(risk: dict) -> list[str]:
    """Assemble KB snippets relevant to this risk's scope."""
    parts: list[str] = []
    scope_ids: list[str] = risk.get("scope_entity_ids") or []

    try:
        from app.kb.entities import get_card
        from app.storage import threat_models_store, decisions_store
        from app.kb.compliance import find_evidence

        for eid in scope_ids[:3]:
            card = get_card(eid)
            if not card:
                continue
            parts.append(f"## Service: {card['name']}")
            if card.get("description"):
                parts.append(card["description"])
            for ch in (card.get("linked_chunks") or [])[:5]:
                parts.append(f"  chunk: {(ch.get('snippet') or '')[:300]}")

            tm = threat_models_store.latest_for_service(eid)
            if tm:
                threats = tm.get("threats") or []
                if threats:
                    parts.append(f"Threat model v{tm['version']} — "
                                 f"{len(threats)} threats")
                    for t in threats[:4]:
                        parts.append(
                            f"  - {t.get('stride_category','?')}: "
                            f"{t.get('title','?')} "
                            f"(L={t.get('likelihood','?')} I={t.get('impact','?')})"
                        )

            decisions = decisions_store.list_filtered(
                scope_entity_id=eid, status="open", limit=5,
            )
            if decisions:
                parts.append("Open decisions:")
                for d in decisions:
                    parts.append(f"  - [{d['kind']}] {d['title']}")

    except Exception as exc:
        log.debug("context build failed (non-fatal): %s", exc)

    if risk.get("controls"):
        parts.append("Controls claimed in place:")
        for c in risk["controls"]:
            parts.append(f"  - {c}")

    return parts
