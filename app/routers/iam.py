"""IAM policy translator endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.claude import iam_translator
from app.kb import iam as iam_kb

router = APIRouter(prefix="/api/iam")


@router.get("/explain/{policy_id}")
async def explain(policy_id: str) -> dict:
    return iam_translator.explain(policy_id)


@router.get("/risks")
async def risks(limit: int = 10) -> dict:
    return iam_kb.find_risks(limit=limit)
