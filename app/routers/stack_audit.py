"""Security Stack Audit — structured inventory of 15 capability categories.

Routes:
  GET  /stack-audit            — serve the stack audit page
  POST /api/stack-audit/save   — save one or more category assessments
  GET  /api/stack-audit        — return all 15 categories with current state
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.role import get_state
from app.storage import asset_inventory_store as inv_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Common tools pre-populated per category. Shown as dropdown options in the UI;
# users can select "Other…" to enter a custom value not on this list.
TOOL_OPTIONS: dict[str, list[str]] = {
    "Identity Provider (SSO/LDAP)": [
        "Okta", "Azure AD / Entra ID", "Google Workspace", "OneLogin",
        "Ping Identity", "JumpCloud", "Auth0",
    ],
    "Multi-Factor Authentication": [
        "Duo Security", "Okta Verify", "Microsoft Authenticator",
        "Google Authenticator", "YubiKey", "Authy",
    ],
    "Secrets Management": [
        "HashiCorp Vault", "AWS Secrets Manager", "Azure Key Vault",
        "GCP Secret Manager", "CyberArk", "Doppler", "1Password Secrets",
    ],
    "SIEM / Log Aggregation": [
        "Splunk", "Elastic / ELK", "Microsoft Sentinel", "Sumo Logic",
        "Datadog", "CrowdStrike Falcon", "IBM QRadar",
    ],
    "Web Application Firewall (WAF)": [
        "Cloudflare WAF", "AWS WAF", "Fastly", "Akamai",
        "F5 Advanced WAF", "Imperva", "Barracuda",
    ],
    "Endpoint Detection & Response (EDR)": [
        "CrowdStrike Falcon", "SentinelOne", "Microsoft Defender for Endpoint",
        "Carbon Black", "Cylance", "Palo Alto Cortex XDR",
    ],
    "Vulnerability Scanner": [
        "Qualys VMDR", "Tenable / Nessus", "Rapid7 InsightVM",
        "Snyk", "Wiz", "OpenVAS",
    ],
    "Data Loss Prevention (DLP)": [
        "Microsoft Purview", "Symantec DLP", "Forcepoint",
        "Nightfall", "Digital Guardian", "Varonis",
    ],
    "Network Segmentation": [
        "Palo Alto NGFW", "Cisco ASA", "Fortinet FortiGate",
        "Check Point", "Zscaler", "Illumio",
    ],
    "Backup & Recovery": [
        "Veeam", "Commvault", "Rubrik", "AWS Backup",
        "Azure Backup", "Cohesity", "Zerto",
    ],
    "Patch Management": [
        "Microsoft WSUS / SCCM", "Ivanti", "Tanium",
        "Automox", "ManageEngine Endpoint", "BigFix",
    ],
    "Security Training Platform": [
        "KnowBe4", "Proofpoint Security Awareness", "Cofense",
        "SANS", "Mimecast Awareness", "Cybrary",
    ],
    "Bug Bounty / Penetration Testing": [
        "HackerOne", "Bugcrowd", "Synack", "Cobalt", "Internal red team",
    ],
    "Container / Supply Chain Security": [
        "Snyk", "Aqua Security", "Prisma Cloud", "Sysdig",
        "Trivy", "GitHub Advanced Security", "Anchore",
    ],
    "Cloud Security Posture Management (CSPM)": [
        "Wiz", "Prisma Cloud", "Orca Security", "Lacework",
        "AWS Security Hub", "Microsoft Defender for Cloud",
    ],
}


class SaveCategoryBody(BaseModel):
    capability_category: str
    tool_name: str | None = None
    deployment_status: str = "none"
    coverage_notes: str | None = None
    known_gaps: str | None = None


@router.get("/stack-audit", response_class=HTMLResponse)
def stack_audit_page(request: Request):
    state = get_state()
    categories = inv_store.get_all()
    completion_pct = inv_store.completion_percentage()
    return templates.TemplateResponse(
        request=request,
        name="stack_audit.html",
        context={
            "state": state,
            "categories": categories,
            "completion_pct": completion_pct,
            "tool_options": TOOL_OPTIONS,
        },
    )


@router.get("/api/stack-audit")
def get_stack_audit() -> JSONResponse:
    return JSONResponse({
        "categories": inv_store.get_all(),
        "completion_pct": inv_store.completion_percentage(),
    })


@router.post("/api/stack-audit/save")
def save_category(body: SaveCategoryBody) -> JSONResponse:
    if body.capability_category not in inv_store.CAPABILITY_CATEGORIES:
        return JSONResponse({"error": "Unknown category"}, status_code=422)
    iid = inv_store.upsert(
        capability_category=body.capability_category,
        tool_name=body.tool_name or None,
        deployment_status=body.deployment_status,
        coverage_notes=body.coverage_notes or None,
        known_gaps=body.known_gaps or None,
    )
    return JSONResponse({
        "ok": True,
        "id": iid,
        "completion_pct": inv_store.completion_percentage(),
    })
