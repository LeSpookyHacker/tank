"""Quick-Start Intake Interview — the front door for first-hire onboarding.

A 20-question structured interview that seeds the entity graph and generates
a Day-1 brief before any document is uploaded.

Routes:
  GET  /intake                   — serve the intake interview UI
  GET  /api/intake/state         — returns current intake state
  POST /api/intake/start         — create a fresh interview record
  POST /api/intake/complete      — save answers, seed entities, kick off Day-1 brief
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state, update_state
from app.storage import intake_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.intake")

# ── 20 intake questions ────────────────────────────────────────────────────────
QUESTIONS: list[dict] = [
    {
        "id": "q1_product",
        "text": "What does your company build?",
        "hint": "Product or service description",
        "input_type": "freetext",
        "required": True,
    },
    {
        "id": "q2_customers",
        "text": "Who are your customers?",
        "hint": "Select all that apply",
        "input_type": "chips",
        "options": ["Consumers", "SMB", "Enterprise", "Government", "Internal"],
        "required": True,
    },
    {
        "id": "q3_data_types",
        "text": "What sensitive data does the company handle?",
        "hint": "Select all that apply",
        "input_type": "chips",
        "options": [
            "PII", "Payment card data", "Health data", "Financial records",
            "Credentials", "IP", "Regulated data", "None I'm aware of",
        ],
        "required": True,
    },
    {
        "id": "q4_cloud_providers",
        "text": "What cloud providers does the company use?",
        "hint": "Select all that apply",
        "input_type": "chips",
        "options": ["AWS", "GCP", "Azure", "On-prem", "Other"],
        "required": True,
    },
    {
        "id": "q5_services",
        "text": "What are the names of your most important services or applications?",
        "hint": "Comma-separated or one per line",
        "input_type": "freetext",
        "required": True,
    },
    {
        "id": "q6_owners",
        "text": "Who owns those services?",
        "hint": "Team names or individual names",
        "input_type": "freetext",
        "required": False,
    },
    {
        "id": "q7_eng_size",
        "text": "How large is the engineering org?",
        "hint": "Approximate headcount",
        "input_type": "chips",
        "options": ["1–10", "11–50", "51–200", "200+"],
        "required": False,
    },
    {
        "id": "q8_idp",
        "text": "Does the company have an identity provider (e.g. Okta, Google Workspace)?",
        "hint": "e.g. 'Okta' or 'No'",
        "input_type": "yes_name",
        "options": ["Yes", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q9_mfa",
        "text": "Is MFA enforced for internal systems?",
        "hint": "",
        "input_type": "chips",
        "options": ["Yes, everywhere", "Yes, some systems", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q10_secrets_manager",
        "text": "Does the company have a secrets manager (e.g. Vault, AWS Secrets Manager)?",
        "hint": "e.g. 'HashiCorp Vault' or 'No'",
        "input_type": "yes_name",
        "options": ["Yes", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q11_security_tools",
        "text": "Are there any existing security tools in place?",
        "hint": "e.g. 'We have Snyk, no SIEM, no WAF'",
        "input_type": "freetext",
        "required": False,
    },
    {
        "id": "q12_incidents",
        "text": "Has the company ever had a security incident or breach?",
        "hint": "If yes, brief description is helpful",
        "input_type": "yes_detail",
        "options": ["Yes", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q13_compliance",
        "text": "Is there any existing compliance requirement or obligation?",
        "hint": "Select all that apply",
        "input_type": "chips",
        "options": ["SOC 2", "ISO 27001", "PCI-DSS", "HIPAA", "GDPR", "None", "Not sure"],
        "required": False,
    },
    {
        "id": "q14_customer_compliance",
        "text": "Do any enterprise customers require compliance evidence as a condition of contract?",
        "hint": "",
        "input_type": "chips",
        "options": ["Yes", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q15_stack",
        "text": "What is the company's primary programming language or stack?",
        "hint": "e.g. 'Python/Django, React, PostgreSQL'",
        "input_type": "freetext",
        "required": False,
    },
    {
        "id": "q16_code_location",
        "text": "Where does the company's code live?",
        "hint": "",
        "input_type": "chips",
        "options": ["GitHub", "GitLab", "Bitbucket", "Other", "Not sure"],
        "required": False,
    },
    {
        "id": "q17_staging",
        "text": "Does the company have a staging/production separation?",
        "hint": "",
        "input_type": "chips",
        "options": ["Yes", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q18_dr",
        "text": "Is there a disaster recovery or backup process for critical data?",
        "hint": "",
        "input_type": "chips",
        "options": ["Yes", "No", "Not sure"],
        "required": False,
    },
    {
        "id": "q19_expectations",
        "text": "What does your manager or leadership expect from you in the first 90 days?",
        "hint": "This seeds the 90-day plan priorities",
        "input_type": "freetext",
        "required": False,
    },
    {
        "id": "q20_worries",
        "text": "What are you most worried about security-wise right now?",
        "hint": "This seeds your initial risk hypothesis",
        "input_type": "freetext",
        "required": False,
    },
]

REQUIRED_IDS = {q["id"] for q in QUESTIONS if q.get("required")}


class CompleteIntakeBody(BaseModel):
    interview_id: str
    answers: dict


# ── Page route ─────────────────────────────────────────────────────────────────

@router.get("/intake", response_class=HTMLResponse)
def intake_page(request: Request):
    state = get_state()
    existing = intake_store.get_latest()
    return templates.TemplateResponse(
        request=request,
        name="intake.html",
        context={
            "state": state,
            "questions": QUESTIONS,
            "existing": existing,
        },
    )


# ── API routes ─────────────────────────────────────────────────────────────────

@router.get("/api/intake/state")
def intake_state() -> JSONResponse:
    state = get_state()
    existing = intake_store.get_latest()
    return JSONResponse({
        "intake_completed": state.intake_completed,
        "kb_bootstrap_stage": state.kb_bootstrap_stage,
        "interview": existing,
    })


@router.post("/api/intake/start")
def intake_start() -> JSONResponse:
    iid = intake_store.create()
    return JSONResponse({"interview_id": iid})


@router.post("/api/intake/complete")
async def intake_complete(
    body: CompleteIntakeBody,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    answers = body.answers

    # Validate that the first 5 required questions are answered.
    missing = [qid for qid in REQUIRED_IDS if not answers.get(qid)]
    if missing:
        return JSONResponse(
            {"error": f"Required questions not answered: {missing}"},
            status_code=422,
        )

    intake_store.complete(body.interview_id, answers)

    # Persist org-profile fields to app_state for later Claude context injection.
    state_kwargs: dict = {
        "intake_completed": True,
        "kb_bootstrap_stage": "intake_done",
    }
    if answers.get("q7_eng_size"):
        val = answers["q7_eng_size"]
        state_kwargs["approx_team_size"] = val[0] if isinstance(val, list) else val
    if answers.get("q13_compliance"):
        targets = answers["q13_compliance"]
        if isinstance(targets, list):
            state_kwargs["compliance_targets"] = [
                t for t in targets if t.lower() not in ("none", "not sure")
            ]
    update_state(**state_kwargs)

    background_tasks.add_task(_seed_and_brief, body.interview_id, answers)
    return JSONResponse({"ok": True, "interview_id": body.interview_id})


@router.post("/api/intake/regenerate-day1-brief")
async def regenerate_day1_brief(background_tasks: BackgroundTasks) -> JSONResponse:
    """Re-generate the Day-1 brief from the most recent completed intake interview."""
    existing = intake_store.get_latest()
    if not existing or not existing.get("completed_at"):
        return JSONResponse({"error": "No completed intake interview found"}, status_code=404)
    background_tasks.add_task(_brief_only, existing["id"], existing.get("answers", {}))
    return JSONResponse({"ok": True, "interview_id": existing["id"]})


def _brief_only(interview_id: str, answers: dict) -> None:
    try:
        from app.claude.day1_brief import generate_from_intake
        generate_from_intake(answers)
    except Exception:
        log.exception("Day-1 brief regeneration failed for interview %s", interview_id)


def _seed_and_brief(interview_id: str, answers: dict) -> None:
    """Background task: seed entities then generate Day-1 brief."""
    try:
        from app.claude.intake_seeder import seed_from_answers
        seed_from_answers(interview_id, answers)
    except Exception:
        log.exception("entity seeding failed for interview %s", interview_id)

    try:
        from app.claude.day1_brief import generate_from_intake
        generate_from_intake(answers)
    except Exception:
        log.exception("intake Day-1 brief generation failed for interview %s", interview_id)
