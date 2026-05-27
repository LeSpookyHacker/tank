"""Plain-English IAM policy translation + risk audit.

Two surfaces:
- `explain(policy_id)` — Claude turns the policy JSON into plain
  English with risk callouts. Used by the chat tool +
  `iam_policy_detail.html`.
- `audit()` — ranks all ingested IAMPolicy entities and produces an
  `IAMAuditReport`. Persisted as a Report of kind `iam_audit`.
"""
from __future__ import annotations

import json
import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions
from app.kb.iam import find_risks
from app.schemas import IAMAuditReport, IAMPolicyRisk
from app.storage import entities_store

log = logging.getLogger("tank.iam_translator")


def explain(policy_id: str) -> dict:
    """Return {explanation_md, risks, score} for a single IAMPolicy."""
    ent = entities_store.get_entity(policy_id)
    if not ent or ent["type"] != "IAMPolicy":
        return {"error": "not an IAMPolicy entity"}
    try:
        attrs = json.loads(ent["attrs_json"] or "{}")
    except Exception:
        attrs = {}

    client = get_client()
    try:
        prompt = load_prompt("iam_translator")
    except FileNotFoundError:
        return {"error": "iam_translator prompt missing"}

    body_text = (
        f"# Policy: {apply_redactions(ent['name']).redacted_text}\n\n"
        f"Risk score (parsed): {attrs.get('risk_score')}\n\n"
        f"Callouts (parsed): {attrs.get('risk_callouts')}\n\n"
        f"Description: {apply_redactions(ent.get('description') or '').redacted_text or '—'}"
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": [{"type": "text", "text": body_text}]}],
        )
        log_token_usage("iam_translator.explain", MODEL, getattr(resp, "usage", None))
        explanation = ""
        for block in resp.content or []:
            t = getattr(block, "text", None)
            if t:
                explanation += t
    except Exception as exc:
        log.warning("iam_translator LLM failed: %s", exc)
        explanation = "(LLM call failed; falling back to parsed callouts)"

    return {
        "policy_id": policy_id,
        "policy_name": ent["name"],
        "explanation_md": explanation or "(no explanation)",
        "risk_score": float(attrs.get("risk_score") or 0.0),
        "risks": attrs.get("risk_callouts") or [],
    }


def audit() -> IAMAuditReport:
    """Run an audit over all IAMPolicy entities; return the report."""
    raw = find_risks(limit=50)
    policies: list[IAMPolicyRisk] = []
    for p in raw["policies"]:
        explanation = (
            f"**Risk:** {p['risk_score']:.1f}/10. "
            + "; ".join(p["risk_callouts"])
        )
        policies.append(IAMPolicyRisk(
            policy_name=p["name"], policy_id=p["id"],
            risks=p["risk_callouts"], score=p["risk_score"],
            explanation_md=explanation,
        ))
    top_risks = [p.policy_name for p in policies if p.score >= 7.0][:5]
    summary = (
        f"{len(policies)} policies audited; "
        f"{len(top_risks)} flagged critical (score ≥ 7)."
    )
    return IAMAuditReport(
        policies=policies, summary=summary, top_risks=top_risks,
    )
