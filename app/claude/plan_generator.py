"""90-Day Plan generator for first-hire onboarding."""
from __future__ import annotations

import json
import logging

from app.claude.reports import _build_scope_block
from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.role import get_state
from app.schemas import PlanOutput
from app.storage import intake_store, plan_store

log = logging.getLogger("tank.plan_gen")


def generate() -> str:
    """Generate a 90-day plan from KB context + intake answers. Returns plan ID."""
    state = get_state()

    # Pull intake answers for context
    intake = intake_store.get_latest()
    answers_text = ""
    if intake and intake.get("answers"):
        answers = intake["answers"]
        answers_text = json.dumps(answers, indent=2)

    org_context = []
    if state.user_scope and state.user_scope.org:
        org_context.append(f"Company: {state.user_scope.org}")
    if state.compliance_targets:
        org_context.append(f"Compliance targets: {', '.join(state.compliance_targets)}")
    if state.approx_team_size:
        org_context.append(f"Team size: {state.approx_team_size}")

    user_content = f"""
Organization context:
{chr(10).join(org_context)}

Intake interview answers:
{answers_text or "(no intake answers yet — generate a general first-hire plan)"}

Generate a week-by-week 90-day plan (13 weeks) tailored to this specific company.
Reference the actual service names, team names, and compliance targets mentioned above.
"""

    scope_block = _build_scope_block()
    client = get_client()
    parsed = client.messages.parse(
        model=MODEL,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": load_prompt("plan_generator"),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [
                scope_block,
                {"type": "text", "text": user_content},
            ],
        }],
        output_format=PlanOutput,
    )
    usage = getattr(parsed, "usage", None)
    log_token_usage("plan_generator", MODEL, usage)

    plan_out: PlanOutput = parsed.output
    tasks = [t.model_dump() for t in plan_out.tasks]
    plan_id = plan_store.create(tasks)
    log.info("90-day plan generated: id=%s, %d tasks", plan_id, len(tasks))
    return plan_id
