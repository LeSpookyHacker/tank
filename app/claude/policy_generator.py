"""Security policy generator.

Uses claude-sonnet-4-6 with the KB scope (entity graph + org profile) to
generate first-draft security policies. Mirrors the reports.py pattern.
"""
from __future__ import annotations

import logging

from app.claude.reports import _build_scope_block
from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.role import get_state
from app.storage import policies_store

log = logging.getLogger("tank.policy_gen")

_PROMPT_MAP = {
    "acceptable_use": "policy_acceptable_use",
    "incident_response": "policy_incident_response",
    "secure_sdl": "policy_secure_sdl",
    "vulnerability_management": "policy_vulnerability_management",
    "data_classification": "policy_data_classification",
}


def generate(kind: str) -> str:
    """Generate a first-draft policy. Returns the policy_artifact ID."""
    if kind not in policies_store.POLICY_KINDS:
        raise ValueError(f"unknown policy kind: {kind!r}")

    prompt_name = _PROMPT_MAP[kind]
    base_rules = load_prompt("policy_base")
    specific_prompt = load_prompt(prompt_name)
    system_text = f"{base_rules}\n\n---\n\n{specific_prompt}"

    state = get_state()
    org_context = _build_org_context(state)
    scope_block = _build_scope_block()

    client = get_client()
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    scope_block,
                    {"type": "text", "text": org_context},
                    {"type": "text",
                     "text": f"Generate the {policies_store.POLICY_DISPLAY_NAMES[kind]}."},
                ],
            }],
        )
        usage = getattr(resp, "usage", None)
        log_token_usage(f"policy_gen.{kind}", MODEL, usage)
        content_md_redacted = ""
        for block in resp.content or []:
            t = getattr(block, "text", None)
            if t:
                content_md_redacted += t
        content_md_redacted = content_md_redacted.strip()
    except Exception:
        log.exception("policy generation failed for kind %r", kind)
        raise

    if not content_md_redacted:
        raise RuntimeError(f"policy generation returned empty content for {kind!r}")

    mapping = load_rehydration_map()
    content_md = rehydrate(content_md_redacted, mapping)

    policy_id = policies_store.create(
        kind=kind,
        content_md=content_md,
        content_md_redacted=content_md_redacted,
    )
    log.info("policy generated: kind=%s id=%s", kind, policy_id)
    return policy_id


def _build_org_context(state) -> str:
    parts = ["## Organization context"]
    if state.industry:
        parts.append(f"- Industry: {state.industry}")
    if state.customer_type:
        parts.append(f"- Customer type: {state.customer_type}")
    if state.approx_team_size:
        parts.append(f"- Team size: {state.approx_team_size}")
    if state.compliance_targets:
        parts.append(f"- Compliance targets: {', '.join(state.compliance_targets)}")
    if state.user_scope and state.user_scope.org:
        parts.append(f"- Company: {apply_redactions(state.user_scope.org).redacted_text}")
    return "\n".join(parts)
