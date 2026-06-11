"""Compliance Framework Selection Wizard."""
from __future__ import annotations

import json
import logging
import re

from app.claude.reports import _build_scope_block
from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.redact.engine import apply_redactions
from app.role import get_state

log = logging.getLogger("tank.compliance_wizard")

QUESTIONS = [
    {
        "id": "q1_industry",
        "text": "What industry does the company operate in?",
        "input_type": "chips",
        "options": ["SaaS", "FinTech", "Healthcare", "E-Commerce",
                    "Enterprise Software", "Government", "Other"],
    },
    {
        "id": "q2_customers",
        "text": "Who are the primary customers?",
        "input_type": "chips",
        "options": ["Consumers", "SMB", "Enterprise", "Government",
                    "Healthcare orgs", "Financial institutions"],
    },
    {
        "id": "q3_payment_data",
        "text": "Does the company handle payment card data?",
        "input_type": "chips",
        "options": ["Yes — we process payments", "Yes — we store card data",
                    "No", "Not sure"],
    },
    {
        "id": "q4_health_data",
        "text": "Does the company handle health or medical information?",
        "input_type": "chips",
        "options": ["Yes", "No", "Not sure"],
    },
    {
        "id": "q5_customer_requirement",
        "text": "Do any customers require a specific compliance attestation as a contract condition?",
        "input_type": "chips",
        "options": ["SOC 2", "ISO 27001", "PCI-DSS", "HIPAA BAA",
                    "FedRAMP", "No", "Not sure"],
    },
    {
        "id": "q6_investor_pressure",
        "text": "Does the company have investors or a board asking about compliance?",
        "input_type": "chips",
        "options": ["Yes, SOC 2 specifically", "Yes, but not specific",
                    "No", "Not sure"],
    },
    {
        "id": "q7_government",
        "text": "Does the company sell to US federal government or handle government data?",
        "input_type": "chips",
        "options": ["Yes", "No", "Not sure"],
    },
    {
        "id": "q8_timeline",
        "text": "What is the company's realistic timeline for initial compliance?",
        "input_type": "chips",
        "options": ["3–6 months", "6–12 months", "12–18 months", "No timeline set"],
    },
]


def recommend(answers: dict) -> dict:
    """Run the compliance wizard LLM call. Returns parsed recommendation dict."""
    # SEC-011: redact answers before they leave this machine.
    safe_answers = {k: apply_redactions(str(v)).redacted_text for k, v in answers.items()}
    answers_text = json.dumps(safe_answers, indent=2)
    scope_block = _build_scope_block()
    state = get_state()

    user_content = f"""
Company context:
- Industry: {safe_answers.get('q1_industry', 'unknown')}
- Customers: {safe_answers.get('q2_customers', 'unknown')}
- Compliance targets already known: {', '.join(state.compliance_targets) or 'none'}

Questionnaire answers:
{answers_text}

Generate a ranked compliance framework recommendation for this company.
"""

    client = get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": load_prompt("compliance_wizard"),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [scope_block, {"type": "text", "text": user_content}],
        }],
    )
    usage = getattr(resp, "usage", None)
    log_token_usage("compliance_wizard", MODEL, usage)

    raw = "".join(getattr(b, "text", "") for b in (resp.content or []))
    json_match = re.search(r'\{.*"recommendation".*\}', raw, re.DOTALL)
    if not json_match:
        return {"recommendation": [], "raw": raw}
    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return {"recommendation": [], "raw": raw}
