"""Seed Tank's database with MedScribe-R-Us sample records.

Complements `load_fixtures.py` (which ingests files through the pipeline) by
directly inserting the living-artifact records that are normally created through
Tank's UI, so a fresh clone can demo every feature immediately.

Scenario: you are **LeSpookyHacker**, the **first Application Security hire** at
MedScribe-R-Us (a GCP healthcare-AI company). It is day one — tenure starts
today, so Tank's lens is `map` (orientation mode). The derived artifacts below
are seeded as ready-made examples so every feature page is populated.

Seeds: org + persona (app_state), teams, projects, 2 pre-analyzed DFDs, the risk
register, the vulnerability intake queue (varied triage states), decisions,
glossary, lessons, a tabletop, IR runbooks, a design review, postmortem
artifacts, the stack-audit inventory, a 90-day plan, a report subscription, a
journal entry, and follow-ups. All inserts are idempotent.

Usage:
    python -m scripts.seed_db              # seed everything
    python -m scripts.seed_db --dry-run    # print what would be inserted
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> float:
    return time.time()


def _days_from_now(days: int) -> float:
    return time.time() + days * 86400


def _days_ago(days: int) -> float:
    return time.time() - days * 86400


# ── org + persona ────────────────────────────────────────────────────────────

def seed_org(dry_run: bool) -> None:
    from app.storage.organizations_store import get_org, update_org
    org = get_org()
    if not org or org.get("name") in ("My Organization", "", None):
        if not dry_run:
            update_org(
                name="MedScribe-R-Us",
                description="Healthcare-AI SaaS — turns patient–clinician audio "
                            "into AI SOAP notes written back to Epic/Cerner. "
                            "HIPAA Business Associate, runs on GCP.",
                industry="Healthcare AI / Clinical Documentation",
            )
        print("  [org] Updated org name → MedScribe-R-Us")
    else:
        print(f"  [org] Already set ({org.get('name')!r}) — skipped")


def seed_app_state(dry_run: bool) -> None:
    """Set Day-1 tenure + org profile on app_state (lens stays 'map').

    Only writes columns that exist on app_state (see app/db.py). The company
    *name* lives on the org table (set in seed_org); the persona's name/role
    surface via the org + the imported team-directory Person entities.
    """
    from app.db import LOCK, get_conn
    conn = get_conn()
    # Ensure the single app_state row exists (other NOT NULL cols have defaults).
    with LOCK:
        conn.execute(
            "INSERT OR IGNORE INTO app_state (id, updated_at) VALUES (1, ?)",
            (_now(),))
    row = conn.execute(
        "SELECT tenure_started_at FROM app_state WHERE id = 1").fetchone()
    if row and row["tenure_started_at"]:
        print("  [persona] app_state already set — skipped")
        return
    compliance = json.dumps(["HIPAA / HITECH", "SOC 2 Type II", "HITRUST CSF",
                             "OWASP LLM Top 10", "NIST CSF 2.0"])
    if not dry_run:
        with LOCK:
            conn.execute(
                "UPDATE app_state SET "
                "industry=?, customer_type=?, approx_team_size=?, "
                "compliance_targets=?, internal_tld=?, kb_bootstrap_stage=?, "
                "tenure_started_at=?, onboarded=1, intake_completed=1, "
                "updated_at=? WHERE id=1",
                ("Healthcare AI / Clinical Documentation",
                 "Health systems (B2B, HIPAA covered entities)",
                 "1 (first security hire)", compliance, "medscribe.internal",
                 "ingested", _now(), _now()),
            )
    print("  [persona] First AppSec hire @ MedScribe-R-Us — day 1 (lens=map)")


# ── teams ────────────────────────────────────────────────────────────────────

TEAMS = [
    {"name": "AppSec", "color": "#7c3aed", "icon": "🛡️",
     "description": "Application security program: threat modeling, secure SDLC, "
                    "vuln management, detection engineering. The new function "
                    "LeSpookyHacker is standing up."},
    {"name": "Platform & SRE", "color": "#2563eb", "icon": "☁️",
     "description": "Owns GCP, networking, IAM, Cloud Run, and reliability."},
    {"name": "AI Platform", "color": "#dc2626", "icon": "🤖",
     "description": "Owns the PHI scrubbing layer, summarization, and output "
                    "validation — the Vertex AI pipeline."},
    {"name": "Compliance", "color": "#059669", "icon": "📋",
     "description": "HIPAA Privacy Officer + SOC 2 / HITRUST readiness."},
]


def seed_teams(dry_run: bool) -> dict[str, str]:
    from app.storage.teams_store import insert_team, list_teams
    existing = {t["name"]: t["id"] for t in list_teams(include_archived=True)}
    id_map: dict[str, str] = dict(existing)
    for t in TEAMS:
        if t["name"] in existing:
            print(f"  [team] '{t['name']}' already exists — skipped")
            continue
        if not dry_run:
            id_map[t["name"]] = insert_team(
                name=t["name"], description=t["description"],
                color=t["color"], icon=t["icon"])
        print(f"  [team] Created '{t['name']}'")
    return id_map


# ── projects ─────────────────────────────────────────────────────────────────

def _projects_def(team_ids: dict[str, str]) -> list[dict]:
    appsec = team_ids.get("AppSec", "")
    ai = team_ids.get("AI Platform", "")
    comp = team_ids.get("Compliance", "")
    return [
        {"name": "AI Pipeline Threat Model", "emoji": "🎯", "color": "#dc2626",
         "team_id": ai, "risk_level": "critical", "status": "active",
         "description": "Threat-model the de-id → summarize → validate pipeline",
         "notes": "STRIDE on the AI pipeline DFD. Priorities: PHI scrubbing "
                  "validation (T-007), cross-patient token leak (T-008), "
                  "indirect prompt injection via prior EMR notes (T-014)."},
        {"name": "PHI-in-Logs & Secrets Cleanup", "emoji": "🔒", "color": "#7c3aed",
         "team_id": appsec, "risk_level": "high", "status": "active",
         "description": "Stop PHI/secret leakage across services",
         "notes": "Ship the phi-in-logs SAST rule (T-006); remediate the "
                  "over-broad ci-deploy service account (T-013, IAM-2026-014); "
                  "structured logging everywhere."},
        {"name": "CI/CD Security Gates", "emoji": "⚙️", "color": "#2563eb",
         "team_id": appsec, "risk_level": "high", "status": "active",
         "notes": "Stand up SAST → secrets → SCA → container → DAST gates in CI "
                  "for all Tier-0 service repos. None enforced today."},
        {"name": "SOC 2 / HIPAA Readiness", "emoji": "📋", "color": "#059669",
         "team_id": comp, "risk_level": "medium", "status": "active",
         "description": "Evidence collection before the Sep 2026 SOC 2 window",
         "notes": "Map controls (SOC 2 / HIPAA / NIST CSF), close gaps, collect "
                  "evidence. Audit window opens 2026-09-01."},
    ]


def seed_projects(team_ids: dict[str, str], dry_run: bool) -> None:
    from app.storage.projects_store import create_project, list_projects
    existing = {p["name"] for p in list_projects(include_archived=True)}
    for p in _projects_def(team_ids):
        if p["name"] in existing:
            print(f"  [project] '{p['name']}' already exists — skipped")
            continue
        if not dry_run:
            create_project(
                name=p["name"], description=p.get("description", ""),
                emoji=p["emoji"], color=p["color"],
                team_id=p.get("team_id") or None,
                risk_level=p["risk_level"], status=p["status"],
                notes=p["notes"])
        print(f"  [project] Created '{p['name']}'")


# ── DFD analyses (pre-cached STRIDE) ─────────────────────────────────────────

AI_PIPELINE_MMD = (ROOT / "sample_data/dfd/ai-pipeline-dfd.mmd").read_text() \
    if (ROOT / "sample_data/dfd/ai-pipeline-dfd.mmd").exists() else "flowchart TD\n  ai-pipeline"

EMR_MMD = (ROOT / "sample_data/dfd/emr-integration-dfd.mmd").read_text() \
    if (ROOT / "sample_data/dfd/emr-integration-dfd.mmd").exists() else "flowchart TD\n  emr-integration"

AI_PIPELINE_THREATS = [
    {"threat_id": "T007", "element_id": "PS", "element_label": "phi-scrub-svc",
     "stride_category": "Information Disclosure", "severity": "Critical",
     "cvss_estimate": 9.1,
     "title": "PHI scrubbing false-negative leaks real PHI to Vertex AI",
     "description": "The NER/regex scrubber misses unusual name/date formats; "
                    "unmasked PHI is sent to Vertex AI in the prompt.",
     "mitigation": "Layered NER + regex; labeled-corpus validation suite; scan "
                   "LLM output for PHI patterns from the token map.",
     "references": ["HIPAA 164.514(b)", "OWASP LLM06"], "status": "open"},
    {"threat_id": "T008", "element_id": "OV", "element_label": "output-validation-svc",
     "stride_category": "Information Disclosure", "severity": "Critical",
     "cvss_estimate": 9.3,
     "title": "Cross-patient PHI leak via wrong token map on re-injection",
     "description": "A wrong session's token map re-injects Patient A's PHI into "
                    "Patient B's note.",
     "mitigation": "HMAC session binding (appointment+patient+tenant) validated "
                   "before any substitution; concurrency test coverage.",
     "references": ["CWE-668"], "status": "open"},
    {"threat_id": "T014", "element_id": "AISUM", "element_label": "ai-summarization-svc",
     "stride_category": "Tampering", "severity": "Critical", "cvss_estimate": 8.7,
     "title": "Indirect prompt injection via prior EMR notes",
     "description": "A malicious prior note from the EMR carries an injection "
                    "payload into the LLM context.",
     "mitigation": "Delimit prior notes as untrusted data; output anomaly "
                   "detection; sanitize prompt-control characters.",
     "references": ["OWASP LLM01"], "status": "open"},
    {"threat_id": "T006", "element_id": "AISUM", "element_label": "ai-summarization-svc",
     "stride_category": "Information Disclosure", "severity": "High",
     "cvss_estimate": 7.5,
     "title": "PHI written to application logs",
     "description": "Exception handler logs the request body (transcript) to "
                    "Datadog, which has no PHI BAA.",
     "mitigation": "phi-in-logs SAST rule (blocking); redacting log formatter; "
                   "Datadog PHI scrubbing rules.",
     "references": ["CWE-532"], "status": "open"},
]

EMR_THREATS = [
    {"threat_id": "T009", "element_id": "EMRI", "element_label": "emr-integration-svc",
     "stride_category": "Elevation of Privilege", "severity": "Critical",
     "cvss_estimate": 9.0,
     "title": "Clinician approval-gate bypass",
     "description": "If approval is trusted from the request payload, an "
                    "unapproved AI note can be written to the EMR.",
     "mitigation": "Validate status==approved AND approved_by!=null by reading "
                   "MongoDB directly; never trust the payload.",
     "references": ["CWE-639"], "status": "open"},
    {"threat_id": "T010", "element_id": "EMRI", "element_label": "emr-integration-svc",
     "stride_category": "Spoofing", "severity": "Critical", "cvss_estimate": 8.6,
     "title": "FHIR write-back to the wrong patient",
     "description": "Appointment→patient binding not validated against the SMART "
                    "token's encounter scope could write PHI to the wrong record.",
     "mitigation": "Request encounter-scoped SMART token; validate patient claim "
                   "against the appointment binding; validate FHIR response subject.",
     "references": ["CWE-639"], "status": "open"},
    {"threat_id": "T013", "element_id": "SM", "element_label": "Secret Manager",
     "stride_category": "Elevation of Privilege", "severity": "Critical",
     "cvss_estimate": 9.6,
     "title": "Over-broad service account → total secret compromise",
     "description": "The ci-deploy SA holds Editor + secretmanager.admin "
                    "(IAM-2026-014); one CI compromise yields all PHI secrets.",
     "mitigation": "Per-secret accessor conditions; remove admin/editor from "
                   "ci-deploy; Workload Identity least privilege.",
     "references": ["CWE-269"], "status": "open"},
]


def _seed_one_dfd(name: str, mmd: str, threats: list[dict], dry_run: bool) -> None:
    # Idempotency keyed on the exact diagram hash (the table's UNIQUE column),
    # not a substring of the mermaid source — the diagrams reference each
    # other's service names, so substring matching gives false positives.
    import hashlib
    from app.storage.dfd_store import insert, get_by_hash
    digest = hashlib.sha256(mmd.encode()).hexdigest()
    if get_by_hash(digest):
        print(f"  [dfd] {name} already exists — skipped")
        return
    analysis = {
        "summary": f"Pre-analyzed STRIDE threat model for {name}.",
        "threats": threats,
        "annotated_mermaid": mmd,
    }
    if not dry_run:
        insert(diagram_hash=digest, mermaid_src=mmd, analysis_json=analysis,
               input_format="mermaid", cached=True)
    print(f"  [dfd] Seeded {name} ({len(threats)} threats)")


def seed_dfds(dry_run: bool) -> None:
    _seed_one_dfd("ai-pipeline", AI_PIPELINE_MMD, AI_PIPELINE_THREATS, dry_run)
    _seed_one_dfd("emr-integration", EMR_MMD, EMR_THREATS, dry_run)


# ── risk register ────────────────────────────────────────────────────────────

RISKS = [
    {"title": "PHI scrubbing gap exposes identifiers to Vertex AI",
     "description": "The de-identification layer has no validation suite; a "
                    "false-negative sends real PHI to a third-party LLM (T-007).",
     "category": "data_breach", "il": 4, "ii": 5, "rl": 3, "ri": 5,
     "treatment": "mitigate",
     "rationale": "Build a labeled-corpus validation suite + output PHI scan."},
    {"title": "Indirect prompt injection via prior EMR notes",
     "description": "Untrusted prior-note content reaches the LLM context (T-014).",
     "category": "ai_model_abuse", "il": 3, "ii": 4, "rl": 2, "ri": 4,
     "treatment": "mitigate",
     "rationale": "Delimit prior notes; output anomaly detection."},
    {"title": "Over-broad CI/CD service account in prod",
     "description": "ci-deploy SA holds Editor + Secret Manager admin "
                    "(IAM-2026-014, T-013).",
     "category": "access_control", "il": 3, "ii": 5, "rl": 2, "ri": 5,
     "treatment": "mitigate",
     "rationale": "Scope to per-secret accessor; remove admin/editor."},
    {"title": "PHI leaking into application logs",
     "description": "Services log request bodies; Datadog has no PHI BAA (T-006).",
     "category": "data_breach", "il": 4, "ii": 4, "rl": 2, "ri": 4,
     "treatment": "mitigate",
     "rationale": "Blocking phi-in-logs SAST rule + redacting log formatter."},
    {"title": "Clinician approval gate bypass writes unapproved notes to EMR",
     "description": "Approval enforced client-side could push AI content to the "
                    "EMR without review (T-009).",
     "category": "application", "il": 2, "ii": 5, "rl": 1, "ri": 5,
     "treatment": "mitigate",
     "rationale": "Server-side approval validation from MongoDB (fix shipped)."},
    {"title": "Cross-tenant PHI access via admin authorization flaw",
     "description": "tenant_id trusted from request enables horizontal priv-esc "
                    "across health systems (T-011).",
     "category": "access_control", "il": 3, "ii": 5, "rl": 2, "ri": 5,
     "treatment": "mitigate",
     "rationale": "Enforce tenant_id from verified JWT claim; DAST isolation tests."},
    {"title": "No CI security gates (SAST/SCA/secrets/container/DAST)",
     "description": "Vulnerabilities ship undetected; SOC 2 CC7.1 gap.",
     "category": "supply_chain", "il": 4, "ii": 3, "rl": 2, "ri": 3,
     "treatment": "mitigate",
     "rationale": "Stand up gates per the secure-SDLC policy."},
]


def seed_risks(dry_run: bool) -> None:
    from app.storage.risks_store import create, list_all
    existing = {r["title"] for r in list_all(limit=200)}
    for r in RISKS:
        if r["title"] in existing:
            print(f"  [risk] '{r['title'][:40]}…' exists — skipped")
            continue
        if not dry_run:
            create(title=r["title"], description=r["description"],
                   category=r["category"],
                   inherent_likelihood=r["il"], inherent_impact=r["ii"],
                   residual_likelihood=r["rl"], residual_impact=r["ri"],
                   treatment=r["treatment"], treatment_rationale=r["rationale"],
                   review_at=int(_days_from_now(30)))
        print(f"  [risk] Created '{r['title'][:48]}…'")


# ── vulnerability intake queue ───────────────────────────────────────────────

VULNS = [
    {"title": "PHI logged in transcription-svc exception handler",
     "description": "Request body (transcript) logged to Datadog (T-006).",
     "severity": "high", "source": "manual", "state": "triaged"},
    {"title": "Approval-gate bypass in emr-integration-svc",
     "description": "FHIR write trusted an `approved` flag from the payload (T-009). "
                    "Fixed in staging; verifying in prod.",
     "severity": "critical", "source": "disclosure", "state": "assigned"},
    {"title": "Indirect prompt injection via prior EMR notes",
     "description": "ai-summarization-svc concatenates prior notes without "
                    "delimiting (T-014).",
     "severity": "high", "source": "manual", "state": "open"},
    {"title": "Over-broad ci-deploy service account (IAM-2026-014)",
     "description": "Editor + secretmanager.admin on prod (T-013).",
     "severity": "critical", "source": "scanner", "state": "triaged"},
    {"title": "FastAPI dependency CVE in ai-summarization-svc",
     "description": "Transitive dependency advisory flagged by Dependabot.",
     "severity": "medium", "source": "github_dependabot", "state": "open",
     "cve": "CVE-2024-24762"},
    {"title": "clinician-portal missing security headers (CSP/HSTS)",
     "description": "No CSP/HSTS/X-Frame-Options; relying on Cloud Armor only.",
     "severity": "low", "source": "scanner", "state": "closed"},
    {"title": "tenant_id read from x-tenant-id header in clinician-portal",
     "description": "Horizontal privilege escalation risk (T-011).",
     "severity": "high", "source": "scanner", "state": "assigned"},
]


def seed_vulns(dry_run: bool) -> None:
    from app.storage.vulnerabilities_store import (
        create, triage, assign, close)
    from app.db import get_conn
    # Check against ALL statuses, not just list_open() — otherwise vulns we
    # move to triaged/assigned/closed below would be re-created on a rerun.
    existing = {r["title"] for r in
                get_conn().execute("SELECT title FROM vulnerabilities").fetchall()}
    for v in VULNS:
        if v["title"] in existing:
            print(f"  [vuln] '{v['title'][:40]}…' exists — skipped")
            continue
        if dry_run:
            print(f"  [vuln] Would create '{v['title'][:44]}…' ({v['state']})")
            continue
        vid = create(title=v["title"], description=v["description"],
                     severity=v["severity"], source=v["source"],
                     cve_id=v.get("cve"))
        st = v["state"]
        if st in ("triaged", "assigned", "closed"):
            triage(vid, severity=v["severity"], notes="Triaged during first-week review.")
        if st == "assigned":
            assign(vid, assigned_to="LeSpookyHacker", due_at=int(_days_from_now(14)))
        if st == "closed":
            close(vid, reason="wont_fix",
                  accepted_rationale="Low risk; headers added at the edge via Cloud Armor.")
        print(f"  [vuln] Created '{v['title'][:44]}…' ({st})")


# ── decisions log ────────────────────────────────────────────────────────────

DECISIONS = [
    {"title": "No un-scrubbed PHI may ever reach Vertex AI",
     "kind": "security_invariant", "expires": None,
     "body": "Only HIPAA Safe-Harbor de-identified text crosses the VPC Service "
             "Controls perimeter to Vertex AI. Enforced by the PHI Scrubbing "
             "Layer + an output PHI scan. Non-negotiable.",
     "rationale": "Sending PHI to a third-party LLM without de-id is a breach."},
    {"title": "Clinician approval is enforced server-side from MongoDB only",
     "kind": "security_invariant", "expires": None,
     "body": "EMR Integration validates approval state by reading MongoDB; the "
             "request payload's approval flag is ignored.",
     "rationale": "Safety-critical gate; never trust the client (T-009)."},
    {"title": "Accept fail-closed ABAC availability cost",
     "kind": "accepted_risk", "expires": None,
     "body": "If the ABAC care-team service is unavailable, access is denied "
             "(clinicians see an error) rather than fail-open.",
     "rationale": "Unauthorized PHI access is worse than a brief outage."},
    {"title": "Defer RDS-style IAM migration; remediate ci-deploy SA first",
     "kind": "deferred_fix", "expires_days": 21,
     "body": "Prioritize removing Editor/secretmanager.admin from the ci-deploy "
             "SA (IAM-2026-014) before broader IAM hardening.",
     "rationale": "ci-deploy is the highest blast-radius finding (T-013)."},
]


def seed_decisions(dry_run: bool) -> None:
    from app.storage.decisions_store import create, list_filtered
    existing = {d["title"] for d in list_filtered(limit=200)}
    for d in DECISIONS:
        if d["title"] in existing:
            print(f"  [decision] '{d['title'][:40]}…' exists — skipped")
            continue
        expires = None
        if d.get("expires_days"):
            expires = int(_days_from_now(d["expires_days"]))
        if not dry_run:
            create(title=d["title"], body_md=d["body"],
                   body_md_redacted=d["body"], kind=d["kind"],
                   rationale=d["rationale"], expires_at=expires)
        print(f"  [decision] Created '{d['title'][:44]}…' ({d['kind']})")


# ── glossary ─────────────────────────────────────────────────────────────────

GLOSSARY = [
    ("PHI", "Protected Health Information — individually identifiable health data under HIPAA."),
    ("SOAP note", "Subjective/Objective/Assessment/Plan — the structured clinical note format MedScribe generates."),
    ("FHIR", "Fast Healthcare Interoperability Resources — the HL7 R4 API standard used to write notes back to Epic/Cerner."),
    ("SMART on FHIR", "OAuth 2.0 profile for FHIR; scopes tokens to a specific patient/encounter."),
    ("BAA", "Business Associate Agreement — the HIPAA contract between MedScribe and each customer health system."),
    ("CMEK", "Customer-Managed Encryption Key — per-tenant key in Cloud KMS protecting audio in GCS."),
    ("token map", "The session-scoped mapping from de-identification tokens back to real PHI values; never leaves the platform."),
    ("ABAC", "Attribute-Based Access Control — enforces HIPAA 'minimum necessary' via care-team relationships."),
    ("de-identification", "Removing PHI per HIPAA Safe Harbor before LLM processing."),
    ("prompt injection", "Manipulating an LLM via crafted input; here, indirect injection via prior EMR notes (T-014)."),
    ("Workload Identity", "GCP service-to-service auth with no key files on disk."),
    ("VPC Service Controls", "GCP perimeter that prevents data exfiltration outside an allowed boundary."),
]


def seed_glossary(dry_run: bool) -> None:
    from app.storage.glossary_store import upsert, list_pending, list_confirmed
    existing = {t["term"].lower() for t in (list_pending(200) + list_confirmed(200))}
    for term, definition in GLOSSARY:
        if term.lower() in existing:
            print(f"  [glossary] '{term}' exists — skipped")
            continue
        if not dry_run:
            upsert(term=term, definition=definition, confirmed=False)
        print(f"  [glossary] Proposed '{term}'")


# ── lessons ──────────────────────────────────────────────────────────────────

LESSONS = [
    {"title": "PHI-in-logs is the most likely daily HIPAA violation",
     "body": "Default exception logging echoed a transcript to Datadog. Tooling "
             "(blocking SAST rule) must catch this — manual review won't scale.",
     "tags": ["phi", "logging", "hipaa", "sast"]},
    {"title": "Enforce safety-critical gates server-side from authoritative state",
     "body": "The approval gate was bypassable because it trusted the request "
             "payload. Read state from the database, never the client.",
     "tags": ["authz", "approval-gate", "secure-design"]},
    {"title": "Cost is an availability control in metered AI pipelines",
     "body": "A client retry loop caused a 22× Speech-to-Text bill and delayed "
             "real notes. Bound spend with per-tenant quotas + dedup.",
     "tags": ["availability", "cost", "rate-limiting"]},
    {"title": "Treat all LLM output as untrusted",
     "body": "Vertex AI output can hallucinate or carry injected instructions; "
             "validate schema and scan for PHI before use.",
     "tags": ["llm", "ai-security", "validation"]},
    {"title": "Least-privilege the CI/CD identity first",
     "body": "The highest-blast-radius finding was the ci-deploy SA holding "
             "admin. The deploy identity is a top target — scope it tightly.",
     "tags": ["iam", "least-privilege", "ci-cd"]},
]


def seed_lessons(dry_run: bool) -> None:
    from app.storage.lessons_store import create, search
    existing = {l["title"] for l in search("", limit=200)}
    for l in LESSONS:
        if l["title"] in existing:
            print(f"  [lesson] '{l['title'][:40]}…' exists — skipped")
            continue
        if not dry_run:
            create(title=l["title"], body_md=l["body"],
                   body_md_redacted=l["body"], source_kind="manual",
                   source_id="seed", tags=l["tags"])
        print(f"  [lesson] Created '{l['title'][:44]}…'")


# ── tabletop ─────────────────────────────────────────────────────────────────

def seed_tabletop(dry_run: bool) -> None:
    from app.storage.tabletops_store import create, list_all
    title = "Cross-Tenant PHI Breach via Admin Authorization Flaw"
    if any(title in (t.get("scenario_md") or "") for t in list_all(limit=100)):
        print("  [tabletop] scenario already exists — skipped")
        return
    scenario_md = (
        f"# Tabletop: {title}\n\n"
        "A Clinic Admin at Health System A reports they can see clinician "
        "accounts belonging to Health System B in the Admin Portal. Exercise the "
        "team's response to a suspected cross-tenant PHI exposure (T-011)."
    )
    injects = [
        {"time": "T+0", "event": "Clinic Admin A reports seeing Tenant B data.",
         "question": "Who declares the incident? What is recorded first?"},
        {"time": "T+10m", "event": "audit_events confirms 3 cross-tenant reads.",
         "question": "Is this a reportable breach? Who decides?"},
        {"time": "T+30m", "event": "Root cause: tenant_id trusted from the request.",
         "question": "How do you contain without taking the portal fully down?"},
        {"time": "T+2h", "event": "Scope: 2 tenants, ~40 patient records exposed.",
         "question": "What are the HITECH notification obligations and timeline?"},
    ]
    participants = ("LeSpookyHacker (AppSec), Aanya Krishnan (CTO), "
                    "Tom Bryce (HIPAA Privacy Officer), Dana Okafor (Platform)")
    if not dry_run:
        create(scenario_md=scenario_md, threat_kind="Elevation of Privilege",
               injects=injects, participants=participants)
    print(f"  [tabletop] Created '{title}'")


# ── IR runbooks ──────────────────────────────────────────────────────────────

IR_RUNBOOKS = [
    {"scenario": "PHI breach (unauthorized access/disclosure of PHI)",
     "severity": "SEV-1",
     "body": "See runbooks/phi-breach-response. Record discovery time first "
             "(HITECH 60-day clock), contain the credential/CMEK, preserve "
             "audit_events, scope via audit log, notify covered entities."},
    {"scenario": "LLM prompt-injection incident (T-014)",
     "severity": "SEV-2",
     "body": "Quarantine the affected note, capture the de-identified prompt + "
             "session_id (no raw PHI), find the source (prior note vs scrub gap), "
             "disable prior-note context for the tenant, notify the clinician."},
]


def seed_ir_runbooks(dry_run: bool) -> None:
    from app.storage.ir_runbooks_store import create, list_all
    existing = {r.get("threat_scenario") for r in list_all(limit=100)}
    for r in IR_RUNBOOKS:
        if r["scenario"] in existing:
            print(f"  [ir] '{r['scenario'][:40]}…' exists — skipped")
            continue
        if not dry_run:
            create(threat_scenario=r["scenario"], runbook_md=r["body"],
                   runbook_md_redacted=r["body"], severity_trigger=r["severity"],
                   contacts=["Aanya Krishnan (CTO)", "Tom Bryce (Privacy Officer)"],
                   escalation=["AppSec on-call", "CTO", "CEO"])
        print(f"  [ir] Created runbook '{r['scenario'][:44]}…'")


# ── design review ────────────────────────────────────────────────────────────

def seed_design_review(dry_run: bool) -> None:
    from app.storage.design_reviews_store import create, list_all
    title = "Design Review: PHI Scrubbing Validation Harness"
    if any(d.get("title") == title for d in list_all(limit=100)):
        print("  [design-review] already exists — skipped")
        return
    body = (
        "Proposal to add a labeled-corpus validation harness for the PHI "
        "scrubbing layer (addresses T-007). Runs in CI; fails the build if "
        "recall on the labeled PHI set drops below threshold; emits a metric "
        "for the security-program dashboard."
    )
    checklist = [
        {"item": "Threat model updated for the new component", "status": "pass"},
        {"item": "No new PHI egress paths", "status": "pass"},
        {"item": "Secrets via Secret Manager only", "status": "pass"},
        {"item": "Logging excludes PHI", "status": "fail"},
        {"item": "Rollback plan documented", "status": "na"},
    ]
    if not dry_run:
        create(title=title, body_md=body, body_md_redacted=body,
               requester="Marcus Lee (AI Platform)", checklist=checklist)
    print(f"  [design-review] Created '{title}'")


# ── postmortem artifacts ─────────────────────────────────────────────────────

POSTMORTEMS = [
    {"title": "PHI in Application Logs (Near-Miss)",
     "severity": "sev2", "incident_date": "2026-05-12",
     "services": ["transcription-svc"],
     "fields": {"summary": "Debug log shipped a transcript fragment to Datadog.",
                "impact": "Potential PHI disclosure to a non-BAA log platform; "
                          "no external access; logs purged.",
                "root_cause": "No PHI-in-logs SAST rule; default exception logging.",
                "action_items": "Ship phi-in-logs rule (blocking); redacting formatter."},
     "body": "See postmortems/2026-05-phi-in-logs-near-miss for the full writeup."},
    {"title": "Approval-Gate Bypass Found in Pentest",
     "severity": "sev2", "incident_date": "2026-04-28",
     "services": ["emr-integration-svc"],
     "fields": {"summary": "Pentest bypassed approval via an `approved:true` payload flag.",
                "impact": "Staging only; unapproved AI note could reach a test EMR.",
                "root_cause": "Approval enforced client-side, re-trusted in the payload.",
                "action_items": "Server-side approval from MongoDB (done); detection added."},
     "body": "See postmortems/2026-04-approval-gate-pentest for the full writeup."},
]


def seed_postmortems(dry_run: bool) -> None:
    from app.storage.postmortems_store import create, list_by_status
    existing = {p.get("title") for p in list_by_status(limit=100)}
    for p in POSTMORTEMS:
        if p["title"] in existing:
            print(f"  [postmortem] '{p['title'][:40]}…' exists — skipped")
            continue
        if not dry_run:
            create(title=p["title"], fields=p["fields"], body_md=p["body"],
                   body_md_redacted=p["body"], incident_date=p["incident_date"],
                   severity=p["severity"], services_affected=p["services"])
        print(f"  [postmortem] Created '{p['title'][:44]}…'")


# ── stack-audit inventory ────────────────────────────────────────────────────

ASSET_INVENTORY = [
    # AppSec program tools (standing up during first 90 days)
    ("SAST", "Semgrep (custom rules)", "in_progress", "PHI-in-logs/auth/LLM rules drafted", "Not blocking in CI yet"),
    ("SCA / dependencies", "pip-audit + npm audit + OSV", "planned", "", "No automated scan yet"),
    ("Secrets detection", "gitleaks", "planned", "", "Not enforced pre-commit or CI"),
    ("Container scanning", "Trivy (Artifact Registry)", "partial", "Registry scan on", "No CI gate"),
    ("DAST", "OWASP ZAP", "planned", "", "Auth + tenant-isolation tests needed"),
    ("Detection engineering", "Sigma + Datadog", "in_progress", "5 Sigma rules drafted", "Not deployed to Datadog"),
    ("Vulnerability management", "Tank intake queue", "in_progress", "Queue stood up", "SLAs not enforced org-wide"),
    ("Threat modeling", "STRIDE / DFD", "in_progress", "AI pipeline + EMR modeled", "Remaining Tier-0 services pending"),
    # Platform-owned tools already deployed
    ("Identity Provider (SSO)", "Auth0 (clinicians via health-system SSO/OIDC; admins via Auth0)", "deployed",
     "All user types covered; health-system IdP federation for clinicians",
     "Platform admin FIDO2-only; no SCIM provisioning yet"),
    ("Multi-Factor Authentication", "Auth0 TOTP + WebAuthn; health-system IdP enforces MFA for clinicians", "deployed",
     "Admins: TOTP/WebAuthn required; platform admins: FIDO2 only",
     "Patient magic-link has optional MFA only; SMS MFA explicitly blocked"),
    ("Web Application Firewall (WAF)", "GCP Cloud Armor", "deployed",
     "OWASP CRS + rate limiting per tenant + geo rules on API Gateway",
     "Custom FHIR callback rules still permissive (open item)"),
    ("SIEM / Log Aggregation", "Datadog + GCP Cloud Logging", "partial",
     "Application logs + Cloud Audit Logs flowing; Sigma rules drafted",
     "Sigma rules not yet deployed to Datadog; no PHI BAA on Datadog — PHI must not reach it"),
    ("Backup & Recovery", "SQLite weekly backup (Tank); GCP managed backups for MongoDB Atlas and GCS", "partial",
     "MongoDB Atlas continuous backup on; GCS versioning on; DR region us-east1 provisioned",
     "DR failover untested; no documented RTO/RPO targets yet"),
    ("Cloud Security Posture Management (CSPM)", "None", "gap",
     "",
     "No CSPM tool; manual Terraform policy checks + conftest for IaC; GCP Security Command Center not enabled"),
]


def seed_asset_inventory(dry_run: bool) -> None:
    from app.storage.asset_inventory_store import upsert, get_all
    existing = {a.get("capability_category") for a in get_all()}
    for cap, tool, status, cov, gaps in ASSET_INVENTORY:
        if cap in existing:
            print(f"  [stack-audit] '{cap}' exists — skipped")
            continue
        if not dry_run:
            upsert(capability_category=cap, tool_name=tool,
                   deployment_status=status, coverage_notes=cov, known_gaps=gaps)
        print(f"  [stack-audit] Added '{cap}' ({status})")


# ── 90-day plan ──────────────────────────────────────────────────────────────

PLAN_ITEMS = [
    {"week": 1, "category": "Learn", "task": "Ingest architecture, IAM, PHI data-flow, threat model into the KB", "done": True},
    {"week": 1, "category": "Learn", "task": "Meet Aanya (CTO), Dana (Platform), Marcus (AI), Tom (Privacy)", "done": False},
    {"week": 2, "category": "Assess", "task": "Validate the STRIDE register against the live architecture", "done": False},
    {"week": 2, "category": "Assess", "task": "Stand up the risk register and vuln intake queue", "done": False},
    {"week": 3, "category": "Quick win", "task": "Ship the phi-in-logs SAST rule (blocking) — T-006", "done": False},
    {"week": 4, "category": "Quick win", "task": "Remediate the over-broad ci-deploy SA — T-013 / IAM-2026-014", "done": False},
    {"week": 6, "category": "Build", "task": "Add SAST + secrets + SCA gates to Tier-0 repos", "done": False},
    {"week": 8, "category": "Build", "task": "Build the PHI scrubbing validation harness — T-007", "done": False},
    {"week": 9, "category": "Build", "task": "Deploy the 5 Sigma detections to Datadog", "done": False},
    {"week": 11, "category": "Program", "task": "Author IR runbooks + run the cross-tenant tabletop", "done": False},
    {"week": 12, "category": "Program", "task": "Map SOC 2 / HIPAA controls; start evidence collection", "done": False},
]


def seed_plan(dry_run: bool) -> None:
    from app.storage.plan_store import create, get_latest
    if get_latest():
        print("  [plan] 90-day plan already exists — skipped")
        return
    if not dry_run:
        create(PLAN_ITEMS)
    print(f"  [plan] Created 90-day plan ({len(PLAN_ITEMS)} tasks)")


# ── report subscription ──────────────────────────────────────────────────────

def seed_subscriptions(dry_run: bool) -> None:
    from app.storage.subscriptions_store import subscribe, list_all
    if any(s.get("kind") == "weekly_security_digest" for s in list_all()):
        print("  [subscription] weekly digest already exists — skipped")
        return
    if not dry_run:
        subscribe(kind="weekly_security_digest", cadence="weekly",
                  role_mode="both", scope={})
    print("  [subscription] Subscribed to weekly_security_digest")


# ── journal (Day 1) ──────────────────────────────────────────────────────────

def seed_journal(dry_run: bool) -> None:
    from app.storage.journal_store import upsert_for_today, get_today
    if get_today():
        print("  [journal] entry for today already exists — skipped")
        return
    body = (
        "Day one as the first AppSec hire. Spent the morning loading the "
        "architecture, IAM design, PHI data-flow and the STRIDE register into "
        "Tank. First impressions: the PHI scrubbing layer (no validation suite) "
        "and the over-broad CI deploy identity feel like the scariest items. "
        "Approval-gate fix already landed from the pentest — good sign. Next: "
        "meet the platform and AI leads, and turn the STRIDE register into a "
        "real risk register."
    )
    if not dry_run:
        upsert_for_today(body=body, body_redacted=body)
    print("  [journal] Wrote day-1 journal entry")


# ── follow-ups ───────────────────────────────────────────────────────────────

FOLLOWUPS = [
    {"title": "Ask Dana to scope down the ci-deploy SA (remove admin/editor)", "days": 3},
    {"title": "Confirm Speech-to-Text + Vertex AI BAAs with Tom (Privacy Officer)", "days": 7},
    {"title": "Get a labeled PHI corpus from Marcus for the scrubber test harness", "days": 10},
]


def seed_followups(dry_run: bool) -> None:
    from app.storage.followups_store import create, list_by_status
    existing = {f["title"] for f in list_by_status("open", limit=200)}
    for f in FOLLOWUPS:
        if f["title"] in existing:
            print(f"  [followup] '{f['title'][:40]}…' exists — skipped")
            continue
        if not dry_run:
            create(title=f["title"], source_kind="manual",
                   due_at=_days_from_now(f["days"]))
        print(f"  [followup] Created '{f['title'][:44]}…'")


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be inserted, change nothing")
    args = ap.parse_args(argv)
    dry = args.dry_run

    # Force DB init before any store imports.
    from app.db import get_conn
    get_conn()

    print("Seeding MedScribe-R-Us sample records"
          + (" (DRY RUN)" if dry else "") + " ...\n")

    print("Organization");        seed_org(dry)
    print("Persona / app_state"); seed_app_state(dry)
    print("Teams");               team_ids = seed_teams(dry)
    print("Projects");            seed_projects(team_ids, dry)

    for label, fn in [
        ("DFD analyses", seed_dfds),
        ("Risk register", seed_risks),
        ("Vulnerabilities", seed_vulns),
        ("Decisions", seed_decisions),
        ("Glossary", seed_glossary),
        ("Lessons", seed_lessons),
        ("Tabletop", seed_tabletop),
        ("IR runbooks", seed_ir_runbooks),
        ("Design review", seed_design_review),
        ("Postmortems", seed_postmortems),
        ("Stack-audit inventory", seed_asset_inventory),
        ("90-day plan", seed_plan),
        ("Report subscription", seed_subscriptions),
        ("Journal", seed_journal),
        ("Follow-ups", seed_followups),
    ]:
        print(label)
        fn(dry)

    print("\nDone." + (" (dry run — nothing written)" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
