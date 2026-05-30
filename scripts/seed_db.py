"""Seed Tank's database with Helix Robotics sample records.

Complements `load_fixtures.py` (which ingests files through the pipeline) by
directly inserting records for living-artifact features that are normally created
through Tank's UI:

  - Organization name update ("My Organization" → "Helix Robotics")
  - 3 teams (Platform Security, AppSec, Threat Intelligence)
  - 4 projects across teams
  - 2 pre-analyzed DFD records (payments-api, identity-svc) with full threat JSON
  - 4 decisions (security invariant, design choice, accepted risk, deferred fix)
  - 10 glossary terms (unconfirmed — lets you test the confirmation UX)
  - 5 lessons learned (with tags)
  - 1 tabletop scenario (analytics pipeline ransomware)
  - 3 journal entries (week 1/2/3 onboarding)
  - 3 follow-ups with due dates

All inserts are idempotent: records are skipped if an equivalent already exists
(matched by title for decisions/lessons, by term for glossary, etc.).

Usage:
    python -m scripts.seed_db              # seed everything
    python -m scripts.seed_db --dry-run   # print what would be inserted
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

def _days_from_now(days: int) -> float:
    return time.time() + days * 86400


def _days_ago(days: int) -> float:
    return time.time() - days * 86400


# ── org ──────────────────────────────────────────────────────────────────────

def seed_org(dry_run: bool) -> None:
    from app.storage.organizations_store import get_org, update_org
    org = get_org()
    if org and org.get("name") in ("My Organization", ""):
        if not dry_run:
            update_org(
                name="Helix Robotics",
                description="B2B SaaS — payments and identity infrastructure for robotics OEMs",
                industry="FinTech / Industrial IoT",
            )
        print("  [org] Updated org name → Helix Robotics")
    else:
        name = (org or {}).get("name", "<no org>")
        print(f"  [org] Already set ({name!r}) — skipped")


# ── teams ────────────────────────────────────────────────────────────────────

TEAMS = [
    {
        "name": "Platform Security",
        "description": "Owns cross-service security controls, identity hardening, cloud security, and pii-vault.",
        "color": "#7c3aed",
        "icon": "🔐",
    },
    {
        "name": "AppSec",
        "description": "Design reviews, postmortems, threat modeling, and secure SDLC for Helix product engineering.",
        "color": "#2563eb",
        "icon": "🛡️",
    },
    {
        "name": "Threat Intelligence",
        "description": "Detection engineering, incident response, and ATT&CK mapping. Net-new function the first security hire is standing up (previously handled reactively by SRE).",
        "color": "#dc2626",
        "icon": "🔍",
    },
]


def seed_teams(dry_run: bool) -> dict[str, str]:
    """Returns {team_name: team_id}."""
    from app.storage.teams_store import insert_team, list_teams
    existing = {t["name"]: t["id"] for t in list_teams(include_archived=True)}
    id_map: dict[str, str] = dict(existing)

    for t in TEAMS:
        if t["name"] in existing:
            print(f"  [team] '{t['name']}' already exists — skipped")
            continue
        if not dry_run:
            tid = insert_team(
                name=t["name"],
                description=t["description"],
                color=t["color"],
                icon=t["icon"],
            )
            id_map[t["name"]] = tid
        print(f"  [team] Created '{t['name']}'")

    return id_map


# ── projects ──────────────────────────────────────────────────────────────────

def _projects_def(team_ids: dict[str, str]) -> list[dict]:
    ps = team_ids.get("Platform Security", "")
    ap = team_ids.get("AppSec", "")
    return [
        {
            "name": "Auth Hardening Q2 2026",
            "description": "Harden identity-svc and pii-vault authentication",
            "emoji": "🔑",
            "color": "#7c3aed",
            "team_id": ps,
            "risk_level": "high",
            "status": "active",
            "notes": (
                "Scope: identity-svc JWT hardening (HELIX-2110), RDS IAM auth migration "
                "(HELIX-2108), and JWKS emergency revocation runbook. "
                "Also covers pii-vault break-glass alerting (HELIX-2095)."
            ),
        },
        {
            "name": "PII Data Program",
            "description": "Audit and harden pii-vault access, data flows, and compliance",
            "emoji": "🏦",
            "color": "#dc2626",
            "team_id": ps,
            "risk_level": "critical",
            "status": "active",
            "notes": (
                "Priority: CMK deletion protection (HELIX-2111), rate limiting on pii-vault "
                "GET /pii/* endpoints, and automated break-glass alerting (HELIX-2095). "
                "Also tracking analytics cross-account IAM findings HELIX-2098/2099/2100."
            ),
        },
        {
            "name": "Threat Model Coverage",
            "description": "Build and maintain STRIDE threat models for all Tier-0 services",
            "emoji": "🎯",
            "color": "#2563eb",
            "team_id": ap,
            "risk_level": "medium",
            "status": "active",
            "notes": (
                "Goal: threat model every Tier-0 service (identity-svc, payments-api, "
                "dashboard-web, pii-vault) and run STRIDE on DFDs. Track drift monthly."
            ),
        },
        {
            "name": "SOC 2 Evidence Sprint",
            "description": "Evidence collection for 2024-Q1 SOC 2 Type II audit",
            "emoji": "📋",
            "color": "#059669",
            "team_id": ps,
            "risk_level": "medium",
            "status": "archived",
            "notes": (
                "Completed 2024-Q2. Evidence submitted to auditor. "
                "Report received 2024-08-15 (clean opinion). "
                "Next audit: 2025-Q1 — begin evidence collection 2024-Q4."
            ),
        },
    ]


def seed_projects(team_ids: dict[str, str], dry_run: bool) -> None:
    from app.storage.projects_store import create_project, list_projects
    existing_names = {p["name"] for p in list_projects(include_archived=True)}

    for p in _projects_def(team_ids):
        if p["name"] in existing_names:
            print(f"  [project] '{p['name']}' already exists — skipped")
            continue
        if not dry_run:
            create_project(
                name=p["name"],
                description=p["description"],
                emoji=p["emoji"],
                color=p["color"],
                team_id=p.get("team_id") or None,
                risk_level=p["risk_level"],
                status=p["status"],
                notes=p["notes"],
            )
        print(f"  [project] Created '{p['name']}' (risk={p['risk_level']}, status={p['status']})")


# ── DFD analyses ──────────────────────────────────────────────────────────────

PAYMENTS_API_MMD = """\
flowchart TD
  subgraph internet["Internet (Untrusted)"]
    Browser([End User / OEM Portal Browser])
    Stripe([Stripe API External Vendor])
  end
  subgraph vpc["VPC — prod account 999988887777"]
    ALB[ALB / WAF]
    API[payments-api Python FastAPI Tier-0]
    PiiV[pii-vault mTLS only]
    DB[(payments-prod-pg RDS PostgreSQL)]
    Redis[(Redis Session cache No auth)]
    Vault[HashiCorp Vault]
  end
  Browser -->|HTTPS| ALB
  ALB -->|HTTP/2 + JWT Bearer| API
  API -->|mTLS + Vault bearer token| PiiV
  API -->|TLS + dynamic creds| DB
  API -->|HTTPS + API key| Stripe
  API -->|Vault Agent IRSA| Vault
  Vault -->|Dynamic creds TTL 1h| API
  API -->|TLS VPC-private no auth| Redis
  PiiV -->|IAM auth Vault db role| DB
  PiiV -->|AppRole auth| Vault\
"""

PAYMENTS_API_THREATS = [
    {
        "threat_id": "T001",
        "element_id": "ALB",
        "element_label": "ALB / WAF",
        "stride_category": "Spoofing",
        "severity": "High",
        "cvss_estimate": 7.5,
        "title": "JWT Bearer token replay from stolen client token",
        "description": (
            "The ALB forwards JWT Bearer tokens issued by identity-svc to payments-api without "
            "additional validation. A stolen access token (e.g., from XSS on app.helix.io) "
            "can be replayed against payments-api for the token's full 15-minute TTL."
        ),
        "mitigation": (
            "Implement token binding or sender-constrained tokens (DPoP) to tie access tokens "
            "to a specific client certificate or key. As a short-term mitigation, reduce the "
            "access token TTL to 5 minutes and monitor for concurrent sessions from disparate IPs."
        ),
        "references": ["CWE-384", "OWASP A07:2021"],
        "status": "open",
    },
    {
        "threat_id": "T002",
        "element_id": "API",
        "element_label": "payments-api",
        "stride_category": "Tampering",
        "severity": "Medium",
        "cvss_estimate": 5.9,
        "title": "SQL injection via Vault dynamic credential username",
        "description": (
            "Vault dynamic database credentials use a generated username of the form "
            "'v-payments-<random>'. If the ORM constructs queries using this username in "
            "a non-parameterized context (e.g., a debug log or audit trail query), "
            "a compromised Vault could inject SQL. Low likelihood given current ORM usage "
            "but worth validating."
        ),
        "mitigation": (
            "Audit all PostgreSQL queries in payments-api for parameterized query usage. "
            "Ensure no query uses the connected username as a dynamic input. "
            "Add a lint rule (sqlfluff or bandit) to CI to catch string-concatenated queries."
        ),
        "references": ["CWE-89", "OWASP A03:2021"],
        "status": "open",
    },
    {
        "threat_id": "T003",
        "element_id": "API",
        "element_label": "payments-api",
        "stride_category": "Information Disclosure",
        "severity": "Critical",
        "cvss_estimate": 9.1,
        "title": "Stripe restricted API key exposure via environment variable or log leak",
        "description": (
            "The Stripe restricted API key is stored in Vault but injected into the "
            "payments-api process environment via Vault Agent. A process crash with heap dump, "
            "a verbose exception log including the environ dict, or a debug endpoint that "
            "serializes environment variables would expose the key. Stripe keys have no "
            "built-in IP restriction on Helix's account."
        ),
        "mitigation": (
            "Switch Vault Agent to file-based secret injection (tmpfs volume) rather than "
            "environment variable injection. Configure Stripe to restrict key usage to "
            "Helix's Elastic IP range. Enable Stripe's IP allowlist for restricted keys. "
            "Ensure prod builds have exception detail logging disabled."
        ),
        "references": ["CWE-312", "OWASP A02:2021"],
        "status": "open",
    },
    {
        "threat_id": "T004",
        "element_id": "Redis",
        "element_label": "Redis / ElastiCache",
        "stride_category": "Spoofing",
        "severity": "High",
        "cvss_estimate": 7.4,
        "title": "Session token hijack via unauthenticated Redis access",
        "description": (
            "Redis is VPC-private with security groups restricting access to payments-api "
            "and identity-svc pods. However, Redis runs without authentication. "
            "Any internal actor or process with VPC access (e.g., a compromised pod in "
            "the same namespace, or a Lambda function in the VPC) can read or overwrite "
            "session tokens without credentials."
        ),
        "mitigation": (
            "Enable Redis AUTH (password) or migrate to ElastiCache with in-transit "
            "encryption and IAM-based auth (Redis 7.x + ElastiCache RBAC). "
            "At minimum, network-segment Redis to allow only payments-api and identity-svc "
            "SGs — no wildcard VPC access."
        ),
        "references": ["CWE-306", "OWASP A07:2021"],
        "status": "open",
    },
    {
        "threat_id": "T005",
        "element_id": "PiiV",
        "element_label": "pii-vault",
        "stride_category": "Denial of Service",
        "severity": "High",
        "cvss_estimate": 7.1,
        "title": "mTLS certificate rotation failure causes pii-vault outage",
        "description": (
            "pii-vault validates the payments-api mTLS client certificate at the application "
            "layer. If the 30-day cert rotation via Vault PKI fails silently (Vault Agent "
            "restart loop, PKI policy expiry, etc.), payments-api will begin presenting an "
            "expired cert. pii-vault will reject all requests with 403, causing payments-api "
            "to fail all billing-address lookups and blocking the checkout flow."
        ),
        "mitigation": (
            "Add a cert-expiry alert: Datadog monitor on 'days until expiry' of the "
            "payments-api mTLS cert (extractable from Vault metadata). Alert at 7 days. "
            "Add a runbook entry to the service-restart runbook for mTLS cert rotation. "
            "Test cert rotation in staging on a 25-day schedule (before the 30-day boundary)."
        ),
        "references": ["CWE-295", "OWASP A02:2021"],
        "status": "open",
    },
    {
        "threat_id": "T006",
        "element_id": "PiiV",
        "element_label": "pii-vault",
        "stride_category": "Information Disclosure",
        "severity": "Critical",
        "cvss_estimate": 9.3,
        "title": "Bulk PII export via compromised payments-api process",
        "description": (
            "payments-api is the sole authorized caller of pii-vault. There is no rate "
            "limiting on pii-vault's GET /pii/{customer_id} endpoint. A compromised "
            "payments-api process (or a developer with access to its credentials) could "
            "bulk-export all customer billing addresses by iterating customer IDs. "
            "The export would be indistinguishable from normal traffic in current logs."
        ),
        "mitigation": (
            "Implement rate limiting on pii-vault: max 10 requests/min per Vault token. "
            "Add anomaly detection: alert when pii-vault receives >50 GET requests in "
            "5 minutes from the same client cert. Log all reads to a dedicated audit table "
            "with customer_id and requestor identity."
        ),
        "references": ["CWE-770", "OWASP A01:2021"],
        "status": "open",
    },
    {
        "threat_id": "T007",
        "element_id": "Vault",
        "element_label": "HashiCorp Vault",
        "stride_category": "Elevation of Privilege",
        "severity": "Critical",
        "cvss_estimate": 9.8,
        "title": "Vault token exfiltration via compromised payments-api container",
        "description": (
            "payments-api's Vault Agent sidecar stores the Vault token in a tmpfs volume "
            "accessible to the main container. A container escape (CVE in payments-api's "
            "Python dependencies, or a mis-configured pod security policy) could allow "
            "reading the Vault token from /vault/token. With this token, an attacker has "
            "full payments-api Vault policy: database creds, Stripe API key, PKI cert issuance."
        ),
        "mitigation": (
            "Enable Kubernetes Pod Security Standards (Restricted profile) for the payments-api "
            "namespace. Add seccomp and AppArmor profiles to limit syscalls available to the "
            "container. Implement Vault response-wrapping tokens (use-limit=1) for the most "
            "sensitive secrets. Rotate Vault tokens every 1 hour (reduce lease TTL)."
        ),
        "references": ["CWE-269", "OWASP A05:2021"],
        "status": "open",
    },
    {
        "threat_id": "T008",
        "element_id": "DB",
        "element_label": "payments-prod-pg (RDS PostgreSQL)",
        "stride_category": "Repudiation",
        "severity": "Medium",
        "cvss_estimate": 4.3,
        "title": "Missing RDS audit logging for payments-api DB writes",
        "description": (
            "RDS PostgreSQL for payments-api does not have pgaudit enabled. All write "
            "operations (INSERT/UPDATE/DELETE) are unlogged from a compliance standpoint. "
            "If a data modification incident occurs, forensics cannot determine which "
            "application session made the change. Vault dynamic credentials are per-process "
            "but not per-request."
        ),
        "mitigation": (
            "Enable pgaudit on payments-prod-pg: LOG_LEVEL=log, "
            "pgaudit.log='write,ddl'. Ship pgaudit logs to CloudWatch → Datadog. "
            "Add a Datadog alert for unexpected DDL (table drop, schema modification) "
            "outside a maintenance window."
        ),
        "references": ["CWE-778", "OWASP A09:2021"],
        "status": "open",
    },
    {
        "threat_id": "T009",
        "element_id": "API",
        "element_label": "payments-api",
        "stride_category": "Denial of Service",
        "severity": "Medium",
        "cvss_estimate": 5.3,
        "title": "Stripe API rate limit exhaustion via payment flood",
        "description": (
            "payments-api calls Stripe on every payment attempt. An attacker with a valid "
            "account can trigger thousands of payment attempts (all rejected due to invalid "
            "card data) within Stripe's rate limit window, potentially causing Stripe to "
            "temporarily rate-limit Helix's API key. Real customer payments would fail "
            "during the rate-limit window."
        ),
        "mitigation": (
            "Implement per-account payment attempt rate limiting at payments-api: "
            "max 5 failed attempts per 15 minutes per customer_id. Add CAPTCHA on "
            "the payment form after 3 consecutive failures. Monitor Stripe API response "
            "codes 429 in Datadog and alert on spikes."
        ),
        "references": ["CWE-400", "OWASP A04:2021"],
        "status": "open",
    },
    {
        "threat_id": "T010",
        "element_id": "ALB",
        "element_label": "ALB / WAF",
        "stride_category": "Tampering",
        "severity": "Low",
        "cvss_estimate": 3.1,
        "title": "HTTP request smuggling via ALB to payments-api",
        "description": (
            "The ALB uses HTTP/2 for the browser→ALB leg and downgrades to HTTP/1.1 "
            "internally. If payments-api's Uvicorn version does not correctly handle "
            "conflicting Content-Length and Transfer-Encoding headers, HTTP request "
            "smuggling may allow an attacker to inject requests to other users' sessions "
            "being processed concurrently."
        ),
        "mitigation": (
            "Keep Uvicorn and FastAPI updated to versions that include HTTP desync fixes. "
            "Enable ALB access logging and periodically scan for malformed request headers. "
            "Run PortSwigger's HTTP request smuggling scanner against the payments-api "
            "endpoint in staging."
        ),
        "references": ["CWE-444", "OWASP A08:2021"],
        "status": "open",
    },
]

IDENTITY_SVC_MMD = """\
flowchart TD
  subgraph internet["Internet (Untrusted)"]
    Browser([End User / Browser OAuth2 Client])
    Device([OEM Device M2M client_credentials])
    Okta([Okta IdP SSO Federation])
  end
  subgraph vpc["VPC — prod"]
    ALB[ALB / WAF VPN for admin]
    IdSvc[identity-svc Go OIDC Provider Tier-0]
    Admin[Admin Dashboard /admin/* MFA-gated]
    DB[(identity-prod-pg RDS PostgreSQL Password auth HELIX-2108)]
    Redis[(Redis Session + rate-limit No auth VPC-private)]
    Vault[HashiCorp Vault JWT signing Dynamic creds Audit log]
  end
  Browser -->|HTTPS auth code PKCE| ALB
  Device -->|HTTPS client_credentials| ALB
  ALB -->|HTTPS| IdSvc
  ALB -->|HTTPS VPN CIDR only| Admin
  IdSvc -->|Vault Agent IRSA JWT signing Rotate creds| Vault
  IdSvc -->|TLS dynamic password NOT IAM auth| DB
  IdSvc -->|TLS no auth VPC-private Session rate-limit| Redis
  IdSvc -->|HTTPS OIDC federation SSO redirect| Okta
  Admin -->|TLS dynamic password same RDS| DB
  Vault -->|Dynamic creds TTL 8h| IdSvc
  Vault -->|RS256 signing key never leaves Vault| IdSvc\
"""

IDENTITY_SVC_THREATS = [
    {
        "threat_id": "T001",
        "element_id": "IdSvc",
        "element_label": "identity-svc",
        "stride_category": "Spoofing",
        "severity": "High",
        "cvss_estimate": 7.8,
        "title": "OIDC refresh token replay via stolen long-lived token",
        "description": (
            "Refresh tokens have a 7-day TTL and are not device-bound. A stolen refresh "
            "token (e.g., from a mobile device compromise, phishing, or XSS) allows an "
            "attacker to silently obtain new access tokens for 7 days without triggering "
            "any additional MFA challenge. No concurrent session detection exists."
        ),
        "mitigation": (
            "Implement refresh token rotation (each use issues a new refresh token and "
            "invalidates the previous). Add device fingerprinting or origin IP binding "
            "to refresh tokens. Alert on refresh token use from a new device/IP. "
            "Reduce refresh token TTL to 24 hours for high-privilege scopes."
        ),
        "references": ["CWE-384", "OWASP A07:2021"],
        "status": "open",
    },
    {
        "threat_id": "T002",
        "element_id": "Vault",
        "element_label": "HashiCorp Vault",
        "stride_category": "Elevation of Privilege",
        "severity": "Critical",
        "cvss_estimate": 9.8,
        "title": "JWT signing key compromise allows forgery of all Helix tokens",
        "description": (
            "The RS256 JWT signing key is managed by Vault's PKI engine and never written "
            "to disk. However, if Vault itself is compromised (e.g., via a stolen IRSA "
            "token), the attacker can obtain the signing key and forge JWTs for any "
            "Helix user or service. All downstream services (payments-api, pii-vault, etc.) "
            "trust JWTs signed by identity-svc unconditionally."
        ),
        "mitigation": (
            "Implement Vault Sentinel policies to require dual approval for key extraction. "
            "Enable Vault's transit engine audit log and alert on any key export events. "
            "Add a JWKS emergency revocation path: when a signing key is compromised, "
            "immediately remove it from JWKS and force all consumers to re-fetch (HELIX-2110). "
            "Consider HSM-backed Vault for the signing key."
        ),
        "references": ["CWE-347", "OWASP A02:2021"],
        "status": "open",
    },
    {
        "threat_id": "T003",
        "element_id": "DB",
        "element_label": "identity-prod-pg (RDS PostgreSQL)",
        "stride_category": "Elevation of Privilege",
        "severity": "High",
        "cvss_estimate": 7.4,
        "title": "RDS password authentication fallback exposes credentials",
        "description": (
            "identity-svc uses password authentication for RDS via Vault dynamic secrets. "
            "The fallback cached password (24-hour TTL) is stored in Vault Agent's local "
            "file cache. If Vault is unreachable for >24 hours, the stale cached password "
            "provides continued DB access but cannot be rotated. A cache file exfiltration "
            "(container escape or node compromise) exposes a valid DB credential. "
            "IAM auth was not implemented at provisioning time (HELIX-2108)."
        ),
        "mitigation": (
            "Migrate identity-prod-pg to RDS IAM authentication (HELIX-2108). "
            "Schedule migration during the Q2 2026 maintenance window. "
            "As interim mitigation, reduce Vault Agent cache TTL to 1 hour and add a "
            "Datadog alert when Vault is unreachable for >5 minutes."
        ),
        "references": ["CWE-522", "OWASP A02:2021"],
        "status": "open",
    },
    {
        "threat_id": "T004",
        "element_id": "Redis",
        "element_label": "Redis / ElastiCache",
        "stride_category": "Tampering",
        "severity": "High",
        "cvss_estimate": 7.1,
        "title": "Session cache poisoning via unauthenticated Redis write",
        "description": (
            "Redis is VPC-private but unauthenticated. Any process in the VPC with "
            "network connectivity can write arbitrary keys to Redis. An attacker who has "
            "compromised any VPC-connected process could write a crafted session token "
            "entry to impersonate any user, or delete existing sessions causing a "
            "service-wide logout (DoS)."
        ),
        "mitigation": (
            "Enable Redis AUTH with a Vault-managed password, or migrate to ElastiCache "
            "with IAM auth (Redis 7.x RBAC). Network-restrict Redis to only identity-svc "
            "and payments-api security groups (no wildcard VPC CIDR)."
        ),
        "references": ["CWE-306", "OWASP A07:2021"],
        "status": "open",
    },
    {
        "threat_id": "T005",
        "element_id": "Admin",
        "element_label": "Admin Dashboard",
        "stride_category": "Spoofing",
        "severity": "Medium",
        "cvss_estimate": 6.3,
        "title": "CSRF on admin OAuth2 client management endpoints",
        "description": (
            "The /admin/clients endpoint allows creating and updating OAuth2 clients "
            "(client secrets, redirect URIs). If CSRF protection is missing or bypassable "
            "(e.g., SameSite=Lax without an explicit CSRF token), a malicious page could "
            "trick an authenticated admin into registering an attacker-controlled redirect_uri "
            "for an existing client, enabling an OAuth2 authorization code theft attack."
        ),
        "mitigation": (
            "Add a CSRF token to all admin mutation endpoints (POST/PUT/DELETE). "
            "Verify SameSite=Strict on the admin session cookie. "
            "Add CSP header: default-src 'self' to prevent exfiltration via injected resources. "
            "Run OWASP ZAP against /admin/* as part of CI."
        ),
        "references": ["CWE-352", "OWASP A01:2021"],
        "status": "open",
    },
    {
        "threat_id": "T006",
        "element_id": "IdSvc",
        "element_label": "identity-svc",
        "stride_category": "Information Disclosure",
        "severity": "Medium",
        "cvss_estimate": 5.4,
        "title": "JWKS cache staleness exposes 5-minute token forgery window",
        "description": (
            "Consumer services cache the JWKS endpoint response for 5 minutes. If a signing "
            "key is compromised and revoked, forged tokens will be accepted by consumers for "
            "up to 5 minutes after revocation. No emergency revocation mechanism exists "
            "to force consumers to refresh the JWKS immediately (HELIX-2110)."
        ),
        "mitigation": (
            "Implement a JWKS cache-bust endpoint that consumers can be notified to call "
            "(via an internal pub/sub event). Alternatively, push JWKS rotation events "
            "to a Kafka/SQS topic that consumer services subscribe to. "
            "Reduce JWKS cache TTL to 60 seconds as an interim measure."
        ),
        "references": ["CWE-347", "OWASP A02:2021"],
        "status": "open",
    },
    {
        "threat_id": "T007",
        "element_id": "IdSvc",
        "element_label": "identity-svc",
        "stride_category": "Denial of Service",
        "severity": "Medium",
        "cvss_estimate": 6.2,
        "title": "Rate limit exhaustion via enumeration of /oauth2/introspect",
        "description": (
            "The /oauth2/introspect endpoint has no rate limiting (consumers hit it on "
            "every request). A DoS attack targeting this endpoint could cause all "
            "downstream service authentication to fail (payments-api, pii-vault, etc.) "
            "without rate limiting at the ALB. The WAF has a global rate limit but not "
            "endpoint-specific limits."
        ),
        "mitigation": (
            "Add endpoint-level rate limiting to /oauth2/introspect: 100 req/min per "
            "calling service IP. Implement a short-lived introspection cache at consumer "
            "services (30-second TTL with JWT signature pre-verification to avoid "
            "trusting the cache blindly). Add WAF rate rule for this endpoint specifically."
        ),
        "references": ["CWE-400", "OWASP A04:2021"],
        "status": "open",
    },
    {
        "threat_id": "T008",
        "element_id": "Okta",
        "element_label": "Okta IdP",
        "stride_category": "Spoofing",
        "severity": "High",
        "cvss_estimate": 7.6,
        "title": "OIDC federation open redirect via malformed state parameter",
        "description": (
            "The authorization code flow uses a 'state' parameter to prevent CSRF and "
            "to carry the post-login redirect URL. If identity-svc does not validate that "
            "the 'state' redirect target is in an allowlist of Helix-owned domains, an "
            "attacker can craft an authorization URL that redirects the user's browser "
            "to an attacker-controlled site after Okta authentication, leaking the "
            "authorization code in the referrer or via redirect."
        ),
        "mitigation": (
            "Validate the redirect_uri in the state parameter against an allowlist of "
            "registered URIs for the client. Never use the state parameter as a raw "
            "redirect target. Ensure redirect_uri registration in OAuth2 clients uses "
            "exact-match comparison, not prefix matching."
        ),
        "references": ["CWE-601", "OWASP A01:2021"],
        "status": "open",
    },
]


def _dfd_exists(title_substr: str) -> bool:
    from app.db import get_conn
    row = get_conn().execute(
        "SELECT id FROM dfd_analyses WHERE mermaid_src LIKE ?",
        (f"%{title_substr}%",),
    ).fetchone()
    return row is not None


def seed_dfds(dry_run: bool) -> None:
    from app.storage.dfd_store import insert

    # payments-api
    if _dfd_exists("payments-api"):
        print("  [dfd] payments-api analysis already exists — skipped")
    else:
        analysis = {
            "elements": [
                {"element_id": "Browser", "element_label": "End User Browser", "type": "ExternalEntity"},
                {"element_id": "Stripe", "element_label": "Stripe API", "type": "ExternalEntity"},
                {"element_id": "ALB", "element_label": "ALB / WAF", "type": "Process"},
                {"element_id": "API", "element_label": "payments-api", "type": "Process"},
                {"element_id": "PiiV", "element_label": "pii-vault", "type": "Process"},
                {"element_id": "DB", "element_label": "payments-prod-pg", "type": "DataStore"},
                {"element_id": "Redis", "element_label": "Redis Session Cache", "type": "DataStore"},
                {"element_id": "Vault", "element_label": "HashiCorp Vault", "type": "Process"},
            ],
            "threats": PAYMENTS_API_THREATS,
            "annotated_mermaid": PAYMENTS_API_MMD,
        }
        if not dry_run:
            did = insert(
                diagram_hash="seed-payments-api-dfd-v1",
                mermaid_src=PAYMENTS_API_MMD,
                analysis_json=analysis,
                tokens_in=4200,
                tokens_out=3100,
                input_format="mermaid",
                cached=False,
            )
            print(f"  [dfd] Created payments-api analysis  id={did}")
        else:
            print("  [dfd] Would create payments-api analysis (10 threats)")

    # identity-svc
    if _dfd_exists("identity-svc"):
        print("  [dfd] identity-svc analysis already exists — skipped")
    else:
        analysis = {
            "elements": [
                {"element_id": "Browser", "element_label": "End User Browser", "type": "ExternalEntity"},
                {"element_id": "Device", "element_label": "OEM Device M2M", "type": "ExternalEntity"},
                {"element_id": "Okta", "element_label": "Okta IdP", "type": "ExternalEntity"},
                {"element_id": "ALB", "element_label": "ALB / WAF", "type": "Process"},
                {"element_id": "IdSvc", "element_label": "identity-svc", "type": "Process"},
                {"element_id": "Admin", "element_label": "Admin Dashboard", "type": "Process"},
                {"element_id": "DB", "element_label": "identity-prod-pg", "type": "DataStore"},
                {"element_id": "Redis", "element_label": "Redis ElastiCache", "type": "DataStore"},
                {"element_id": "Vault", "element_label": "HashiCorp Vault", "type": "Process"},
            ],
            "threats": IDENTITY_SVC_THREATS,
            "annotated_mermaid": IDENTITY_SVC_MMD,
        }
        if not dry_run:
            did = insert(
                diagram_hash="seed-identity-svc-dfd-v1",
                mermaid_src=IDENTITY_SVC_MMD,
                analysis_json=analysis,
                tokens_in=3800,
                tokens_out=2900,
                input_format="mermaid",
                cached=False,
            )
            print(f"  [dfd] Created identity-svc analysis  id={did}")
        else:
            print("  [dfd] Would create identity-svc analysis (8 threats)")


# ── decisions ─────────────────────────────────────────────────────────────────

DECISIONS = [
    {
        "title": "All JWT signing must use RS256 with Vault-managed keys",
        "kind": "security_invariant",
        "expires_at": None,
        "body_md": (
            "## Decision\n\n"
            "All JWT tokens issued by Helix services (identity-svc, device-registry) "
            "MUST use RS256 (asymmetric) signing with private keys managed exclusively "
            "by HashiCorp Vault's PKI secrets engine.\n\n"
            "## Rationale\n\n"
            "Symmetric algorithms (HS256) require sharing the secret between issuer and "
            "all validators — any validator compromise exposes the signing key. RS256 "
            "allows public-key distribution via JWKS without exposing signing capability. "
            "Vault key management ensures key rotation, audit logging, and no plaintext "
            "key at rest.\n\n"
            "## Enforcement\n\n"
            "- Code review checklist includes JWT signing algorithm check.\n"
            "- CI lint rule: reject any `HS256` string in service code.\n"
            "- Vault ACL prevents any service from extracting the private key directly."
        ),
        "rationale": "RS256 + Vault eliminates symmetric key sharing risk and enables key rotation without redeployment.",
    },
    {
        "title": "Use mTLS for the payments-api → pii-vault channel",
        "kind": "design_choice",
        "expires_at": None,
        "body_md": (
            "## Decision\n\n"
            "The channel between payments-api and pii-vault uses mutual TLS (mTLS) with "
            "client certificates issued by Helix's internal CA (Vault PKI engine). "
            "A Vault bearer token is required as a second factor.\n\n"
            "## Alternatives considered\n\n"
            "- **API key**: Simpler, but a static key with no rotation schedule. "
            "Ruled out after SEC-POL-003 (secrets-management policy) was formalized.\n"
            "- **Service mesh (Istio)**: Provides mTLS automatically but adds operational "
            "complexity for a team of 2 security engineers. Deferred to post-Series-B.\n\n"
            "## Rationale\n\n"
            "mTLS gives cryptographic proof of caller identity at the TLS layer. "
            "Combined with the Vault bearer token, pii-vault has two independent signals "
            "to validate the caller. Short cert TTL (30 days) limits the blast radius "
            "of a compromised cert."
        ),
        "rationale": "mTLS + Vault token provides defense-in-depth for the highest-risk service-to-service channel.",
    },
    {
        "title": "Accept SSRF risk in webhook-router pending HELIX-1822 fix",
        "kind": "accepted_risk",
        "expires_at": _days_from_now(67),  # ~2026-08-01
        "body_md": (
            "## Risk accepted\n\n"
            "webhook-router makes outbound HTTP calls to customer-provided webhook URLs "
            "without denying private IP ranges or the EC2 IMDS endpoint (169.254.169.254). "
            "This creates an SSRF surface where a malicious OEM customer could exfiltrate "
            "the EKS node's IAM role credentials.\n\n"
            "## Risk acceptance rationale\n\n"
            "The webhook feature is contractually committed to 3 OEM customers. Blocking "
            "private IPs requires updating the webhook delivery code and testing against "
            "customer endpoints. Engineering team estimates 2-week effort but the current "
            "sprint is allocated to the Auth Hardening project.\n\n"
            "## Compensating controls\n\n"
            "- IMDSv2 is enforced on all EKS nodes (hop limit = 1), which means a "
            "container-level SSRF cannot directly reach IMDS without a hop increase.\n"
            "- Sigma rule `helix-ec2-metadata-ssrf.yml` alerts on IMDS access patterns.\n"
            "- The node IAM role for ng-general has limited permissions (no `s3:*` on sensitive buckets).\n\n"
            "## Expiry\n\n"
            "This acceptance expires 2026-08-01. HELIX-1822 must be resolved by then or "
            "this decision must be reaffirmed with updated compensating controls."
        ),
        "rationale": "IMDSv2 hop limit + Sigma detection provide partial mitigation while HELIX-1822 is scheduled.",
    },
    {
        "title": "Defer RDS IAM auth migration for identity-prod-pg (HELIX-2108)",
        "kind": "deferred_fix",
        "expires_at": _days_from_now(36),  # ~2026-07-01
        "body_md": (
            "## Deferred fix\n\n"
            "identity-prod-pg currently uses password authentication via Vault dynamic "
            "secrets, not RDS IAM authentication. Migrating to IAM auth requires a "
            "maintenance window and changes to both the application code and the Vault "
            "database secrets engine configuration.\n\n"
            "## Why deferred\n\n"
            "The migration was scoped for Q1 2026 but was postponed due to the Auth "
            "Hardening project taking priority for the identity team. The dynamic secrets "
            "approach provides rotation and short TTLs (mitigating most of the risk), "
            "but the fallback cached credential remains a concern.\n\n"
            "## Deadline\n\n"
            "Must be completed by 2026-07-01 or escalated to the CTO for additional "
            "resource allocation. Tracked in HELIX-2108."
        ),
        "rationale": "Vault dynamic secrets provide acceptable interim risk; IAM auth migration requires a maintenance window scheduled for Q2 2026.",
    },
]


def seed_decisions(dry_run: bool) -> None:
    from app.storage.decisions_store import create, list_filtered
    existing_titles = {d["title"] for d in list_filtered(status=None, limit=500)}

    for dec in DECISIONS:
        if dec["title"] in existing_titles:
            print(f"  [decision] '{dec['title'][:60]}...' already exists — skipped")
            continue
        if not dry_run:
            create(
                title=dec["title"],
                body_md=dec["body_md"],
                kind=dec["kind"],
                expires_at=dec.get("expires_at"),
                rationale=dec.get("rationale"),
            )
        expiry = ""
        if dec.get("expires_at"):
            from datetime import datetime
            expiry = f" (expires {datetime.fromtimestamp(dec['expires_at']).strftime('%Y-%m-%d')})"
        print(f"  [decision] Created '{dec['kind']}' — {dec['title'][:55]}{expiry}")


# ── glossary ──────────────────────────────────────────────────────────────────

GLOSSARY_TERMS = [
    {
        "term": "PAN",
        "definition": "Payment Account Number — the full card number (e.g., 16-digit Visa/MC number). Helix never stores PANs; they are tokenized by Stripe before reaching any Helix service.",
        "aliases": ["Primary Account Number", "card number"],
    },
    {
        "term": "CMK",
        "definition": "Customer-Managed Key — an AWS KMS key where the key material policy is controlled by Helix (not AWS). pii-prod-pg uses a CMK (alias/helix-pii-prod). Required for SOC 2 CC6.1 evidence.",
        "aliases": ["customer managed key", "KMS CMK"],
    },
    {
        "term": "mTLS",
        "definition": "Mutual TLS — both sides of a TLS connection present certificates. Used for payments-api → pii-vault authentication. Provides cryptographic proof of caller identity at the transport layer.",
        "aliases": ["mutual TLS", "client certificates", "client cert auth"],
    },
    {
        "term": "SSRF",
        "definition": "Server-Side Request Forgery — an attacker causes the server to make HTTP requests to an attacker-chosen URL (e.g., EC2 IMDS at 169.254.169.254). Open risk in webhook-router (HELIX-1822).",
        "aliases": ["server side request forgery"],
    },
    {
        "term": "dbt",
        "definition": "Data Build Tool — SQL transformation framework used by Helix's analytics-pipeline. dbt models run in Snowflake against data extracted from RDS replicas. PII masking is applied in the dbt layer (known weakness: HELIX-2031).",
        "aliases": ["data build tool", "dbt Core"],
    },
    {
        "term": "Snowpipe",
        "definition": "Snowflake's auto-ingest mechanism. Helix uses Snowpipe to load data from S3 staging buckets (helix-prod-analytics-staging) into the HELIX_PROD warehouse. Triggered by S3 event notifications.",
        "aliases": ["Snowflake Snowpipe", "auto-ingest"],
    },
    {
        "term": "OEM",
        "definition": "Original Equipment Manufacturer — Helix's customers, who embed Helix's payment and identity APIs into their robotics products. Helix has ~12 OEM customers as of Series B.",
        "aliases": ["original equipment manufacturer", "OEM customer"],
    },
    {
        "term": "device cert",
        "definition": "mTLS client certificate issued to each OEM customer device for authentication to Helix's API. Issued by Vault PKI. 90-day TTL. Private key lives on device; Helix stores only the public cert chain. See INC-2025-0047 (device cert exposure incident).",
        "aliases": ["device certificate", "device mTLS cert", "client cert"],
    },
    {
        "term": "VRT",
        "definition": "Vulnerability Review Team — weekly meeting (Tuesdays 14:00 PST) where security, SRE, and engineering leads review open Dependabot and Inspector findings. Decisions on remediation priority are recorded in Jira.",
        "aliases": ["Vulnerability Review Team", "vuln review"],
    },
    {
        "term": "break-glass",
        "definition": "Emergency access procedure for highly restricted systems (pii-vault, Vault root tokens). Requires two-person approval in Vault. All break-glass access is audit-logged. Used during P0 incidents. Known gap: no automated alert when break-glass is used (HELIX-2095).",
        "aliases": ["break glass", "emergency access", "break-glass access"],
    },
]


def seed_glossary(dry_run: bool) -> None:
    from app.storage.glossary_store import upsert
    for t in GLOSSARY_TERMS:
        if not dry_run:
            upsert(
                term=t["term"],
                definition=t["definition"],
                aliases=t.get("aliases", []),
                confirmed=False,
            )
        print(f"  [glossary] '{t['term']}' (unconfirmed)")


# ── lessons ───────────────────────────────────────────────────────────────────

LESSONS = [
    {
        "title": "Always verify dbt PII masking in staging before promoting to prod",
        "body_md": (
            "## Lesson\n\n"
            "dbt models that mask PII (billing addresses, device serials) can fail silently: "
            "a model error may materialize the table without applying the masking macro, "
            "and downstream consumers see cleartext. dbt tests that check for masking "
            "must be part of the CI gate, not an optional post-deploy step.\n\n"
            "## Source\n\n"
            "Identified during 2026-02 payments outage postmortem review of HELIX-2031 "
            "(analytics-pipeline Snowflake static creds + no masking verification).\n\n"
            "## Action pattern\n\n"
            "Add `dbt test --select tag:pii_masking` to the CI pipeline and block promotion "
            "if any masking test fails."
        ),
        "source_kind": "postmortem",
        "source_id": "inc-2026-02-payments",
        "tags": ["dbt", "pii", "analytics", "ci-cd", "postmortem"],
    },
    {
        "title": "Rotate all Vault tokens org-wide when any service credentials are compromised",
        "body_md": (
            "## Lesson\n\n"
            "When a service's Vault token is compromised, rotating only that service's token "
            "is insufficient — the attacker may have used the token to read other services' "
            "credentials from Vault (if the policy was overly broad). The safe response is to "
            "rotate all AppRole secret_ids and re-issue all Vault tokens, then audit the "
            "Vault access log for the window of compromise.\n\n"
            "## Source\n\n"
            "2026-04 credential leak close call — the affected service had a broader Vault "
            "policy than necessary, which would have allowed reading other services' dynamic "
            "DB creds if the token had been used maliciously.\n\n"
            "## Action pattern\n\n"
            "Define a Vault 'nuclear option' runbook: revoke all tokens, rotate all AppRole "
            "secret_ids, then re-deploy all services in dependency order. Test in staging annually."
        ),
        "source_kind": "postmortem",
        "source_id": "inc-2026-04-credential-leak",
        "tags": ["vault", "incident-response", "credentials", "postmortem"],
    },
    {
        "title": "S3 pre-signed URL TTL must be enforced at the bucket policy layer, not only in application code",
        "body_md": (
            "## Lesson\n\n"
            "Application-layer TTL for S3 pre-signed URLs can be misconfigured (as in "
            "INC-2025-0047) or bypassed. The S3 bucket policy condition "
            "`s3:signatureAge` provides an infrastructure-layer TTL cap that cannot be "
            "overridden by the calling application. Apply this condition to all buckets "
            "that serve sensitive data.\n\n"
            "## Implementation\n\n"
            "```json\n"
            '{"Condition": {"NumericGreaterThan": {"s3:signatureAge": 600}}}\n'
            "```\n"
            "(600 seconds = 10 minutes — the bucket policy will reject any pre-signed URL "
            "older than this, regardless of what TTL the application specified.)\n\n"
            "## Source\n\n"
            "INC-2025-0047 (device cert exposure via 7-day pre-signed URL TTL)."
        ),
        "source_kind": "postmortem",
        "source_id": "inc-2025-0047-device-cert",
        "tags": ["s3", "pre-signed-url", "aws", "pii", "postmortem", "incident-response"],
    },
    {
        "title": "CODEOWNERS and CMDB service ownership must always be in sync — one is authoritative",
        "body_md": (
            "## Lesson\n\n"
            "Helix discovered during the 2026-02 payments outage that CODEOWNERS listed "
            "Marcus Chen as the payments-api owner, while the CMDB (services.csv) listed "
            "Sam Liu. When the incident was declared, initial paging went to Marcus, who "
            "had not touched the service in 6 months. 8 minutes were lost before the "
            "correct on-call (Sam) was reached.\n\n"
            "## Decision\n\n"
            "services.csv is the authoritative source for runtime ownership. CODEOWNERS "
            "is authoritative for code review. They are allowed to diverge, but any "
            "divergence must be documented with a rationale. A weekly CI check compares "
            "the two and opens a Jira ticket if they diverge without explanation.\n\n"
            "## Source\n\n"
            "Post-incident review of 2026-02 payments outage."
        ),
        "source_kind": "user",
        "source_id": "helix-lessons-onboarding-1",
        "tags": ["ownership", "incident-response", "cmdb", "oncall", "process"],
    },
    {
        "title": "GDPR 72-hour notification clock starts from when PII was potentially accessible, not from confirmed exfiltration",
        "body_md": (
            "## Lesson\n\n"
            "During INC-2025-0047 (device cert exposure), Legal clarified that the GDPR "
            "Article 33 72-hour notification window begins when the organization becomes "
            "aware that a breach *may have occurred* — not when exfiltration is confirmed. "
            "Waiting for forensic certainty before notifying can put Helix in breach of "
            "the notification obligation.\n\n"
            "## Practical implication\n\n"
            "If PII was potentially accessible for an extended window (e.g., an open S3 "
            "bucket, an exposed endpoint, an overly permissive IAM role), Legal must be "
            "looped in immediately — not after the forensic investigation is complete. "
            "Legal decides whether to notify, not Engineering.\n\n"
            "## Source\n\n"
            "Legal review following INC-2025-0047."
        ),
        "source_kind": "user",
        "source_id": "helix-lessons-gdpr-1",
        "tags": ["gdpr", "incident-response", "legal", "pii", "compliance"],
    },
]


def seed_lessons(dry_run: bool) -> None:
    from app.storage.lessons_store import create, search
    for les in LESSONS:
        existing = search(les["title"][:40], limit=5)
        if any(e["title"] == les["title"] for e in existing):
            print(f"  [lesson] '{les['title'][:60]}' already exists — skipped")
            continue
        if not dry_run:
            create(
                title=les["title"],
                body_md=les["body_md"],
                source_kind=les["source_kind"],
                source_id=les["source_id"],
                tags=les["tags"],
            )
        print(f"  [lesson] Created '{les['title'][:65]}...'  tags={les['tags'][:3]}")


# ── tabletop ──────────────────────────────────────────────────────────────────

TABLETOP_SCENARIO = """\
# Tabletop: Ransomware via Compromised Analytics Pipeline

## Scenario overview

The analytics-pipeline dbt service account credentials are stolen (via a phishing
email to fatima.al-amin@helixrobotics.com or via a leaked CI/CD secret). The attacker
uses the cross-account IAM role (helix-analytics-prod-read in account 999988887777)
to read all production RDS databases, exfiltrate customer billing addresses to an
external S3 bucket, and then drop tables in the analytics Snowflake warehouse,
demanding a ransom.

## Threat actor

External threat actor. Assumed to have: stolen Snowflake static credential
(from analytics-pipeline Snowflake connector, stored in Vault as static secret HELIX-2031).
Also assumed to have the AWS cross-account role's external ID (found in Terraform state).

## Injects and discussion questions

**T+0 min — Initial access**
> CloudTrail shows an AssumeRole call from account 888877776666 to
> helix-analytics-prod-read in account 999988887777 from an IP outside Helix's
> known CIDR range.

Discussion:
- Who gets paged? How fast?
- Do we have the Vault audit log to cross-check the role assumption?
- Can we immediately revoke the cross-account role without breaking prod analytics?

**T+5 min — Bulk S3 downloads**
> Datadog alerts: helix-s3-bulk-download Sigma rule fires. 2,400 S3 GetObject
> calls against helix-prod-analytics-staging in 3 minutes from the analytics role.

Discussion:
- Can we determine what data was accessed? (S3 access logs, CloudTrail S3 data events)
- Has PII been exfiltrated? (analytics-staging contains masked data per dbt — or does it?)
- What's the GDPR notification threshold here?

**T+15 min — RDS connection spike**
> CloudWatch: identity-prod-pg and payments-prod-pg show 50x normal read connections
> from the analytics account.

Discussion:
- Can rds-db:connect in the cross-account role actually reach pii-prod-pg?
  (Check subnet routing and SGs — it should NOT be able to, but verify.)
- What's our blast radius? Which customer data was in the RDS replicas at T+0?
- Do we have pgaudit on these instances? (Answer: NO — that's a gap, see decisions log.)

**T+25 min — Ransom demand**
> The attacker emails security@helixrobotics.com with proof of exfil (sample of
> customer billing addresses) and demands 50 BTC for deletion of the data and
> decryption of the Snowflake warehouse.

Discussion:
- Who is the decision-maker? (CEO + Legal + CTO)
- Do we pay? What's our policy?
- GDPR notification clock: when did it start? (T+0 or T+25?)
- OEM customer notification obligations (contractual, within 24h)?

## Expected lessons from this tabletop

1. Cross-account IAM role permissions are too broad (HELIX-2098, 2099, 2100).
2. No automated alert on cross-account role assumption from unexpected IP.
3. pgaudit not enabled on prod RDS — forensics would be blind.
4. GDPR notification decision authority must be pre-delegated before an incident.
5. Ransom policy should be documented and approved by board before an incident occurs.
"""


def seed_tabletop(dry_run: bool) -> None:
    from app.storage.tabletops_store import create, list_all
    existing = list_all(limit=100)
    if any("analytics pipeline" in (t.get("scenario_md") or "").lower() for t in existing):
        print("  [tabletop] Analytics pipeline ransomware scenario already exists — skipped")
        return
    if not dry_run:
        tid = create(
            scenario_md=TABLETOP_SCENARIO,
            scope_service_id=None,
            threat_kind="ransomware",
            injects=[
                {"time_offset_min": 0, "title": "CloudTrail: unexpected AssumeRole from foreign IP"},
                {"time_offset_min": 5, "title": "Datadog: S3 bulk download alert fires"},
                {"time_offset_min": 15, "title": "CloudWatch: RDS connection spike from analytics account"},
                {"time_offset_min": 25, "title": "Ransom demand email received"},
            ],
            participants="mei.watanabe, diana.okoro, alice.tanaka, fatima.al-amin, tom.brandt",
        )
        print(f"  [tabletop] Created analytics-pipeline ransomware scenario  id={tid}")
    else:
        print("  [tabletop] Would create analytics-pipeline ransomware scenario (4 injects)")


# ── journal entries ───────────────────────────────────────────────────────────

JOURNAL_ENTRIES = [
    {
        "date_label": "2026-04-28",
        "body": (
            "First day at Helix. Met with Priya and Tom. Key takeaways:\n"
            "- identity-svc is considered the crown jewel — JWT signing key compromise = game over.\n"
            "- pii-vault is highest-risk because it's sole custodian of customer billing addresses.\n"
            "  No one has done a threat model on it recently.\n"
            "- Diana (Senior SRE) carried security reactively before me — my best source on "
            "incident history and the existing Datadog detections. Weekly 1:1 Thursdays.\n"
            "- First 30 days: learn the architecture, meet the service owners, identify the top 3 risks.\n"
            "- TODO: Read all postmortems. Ask Marcus about HELIX-2108 (RDS IAM auth gap)."
        ),
    },
    {
        "date_label": "2026-05-07",
        "body": (
            "Week 2 check-in. Finished reading all postmortems and the architecture docs.\n\n"
            "Biggest concerns so far:\n"
            "1. HELIX-1822 (webhook-router SSRF) — no private IP blocking. IMDSv2 helps but doesn't "
            "   close it completely. Accepted risk expires 2026-08-01 but needs a real fix.\n"
            "2. analytics cross-account IAM role (HELIX-2098/2099/2100) — can read ALL RDS metadata "
            "   and has ListAllMyBuckets. Fatima says the dbt connector needs it but that's not true "
            "   for the RDS DescribeDB* scope.\n"
            "3. pii-vault break-glass alerts (HELIX-2095) — only monthly manual audit. This should "
            "   be an automated Datadog alert.\n\n"
            "Meeting with Marcus next Tuesday about HELIX-2108 status. Alice wants to do a tabletop "
            "on the analytics pipeline scenario before Q3."
        ),
    },
    {
        "date_label": "2026-05-19",
        "body": (
            "Week 3. Ran STRIDE on identity-svc DFD (uploaded identity-svc-dfd.mmd into Tank).\n\n"
            "Top 3 findings:\n"
            "- T002: JWT signing key compromise via Vault IRSA token theft — Critical. "
            "  Vault Sentinel policies would help but we don't have them configured.\n"
            "- T001: Refresh token replay, 7-day window, no rotation — High.\n"
            "- T003: RDS password auth fallback with 24h cache — High. "
            "  Marcus confirmed HELIX-2108 is scheduled for end of June.\n\n"
            "Shared the DFD analysis report with Priya. She wants a similar analysis for pii-vault "
            "before the board meeting on June 15.\n\n"
            "Started draft of the threat model write-up for identity-svc. "
            "Also confirmed with Alice (SRE, Vault admin) that she'll add Vault Sentinel "
            "policies to the Q3 roadmap."
        ),
    },
]


def seed_journal(dry_run: bool) -> None:
    from app.db import LOCK, get_conn
    import uuid as _uuid

    for entry in JOURNAL_ENTRIES:
        existing = get_conn().execute(
            "SELECT id FROM journal_entries WHERE date_label = ?",
            (entry["date_label"],),
        ).fetchone()
        if existing:
            print(f"  [journal] {entry['date_label']} already exists — skipped")
            continue
        if not dry_run:
            jid = _uuid.uuid4().hex
            now = time.time()
            with LOCK:
                get_conn().execute(
                    "INSERT INTO journal_entries "
                    "(id, body, body_redacted, date_label, tenure_day, extracted_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (jid, entry["body"], entry["body"], entry["date_label"], 0, "{}", now),
                )
        print(f"  [journal] Created entry for {entry['date_label']}")


# ── follow-ups ────────────────────────────────────────────────────────────────

FOLLOWUPS = [
    {
        "title": "Ask Marcus about HELIX-2108 status (RDS IAM auth for identity-prod-pg)",
        "body": "Confirm whether the Q2 2026 maintenance window is scheduled. If not, escalate to Priya. Deferred-fix decision expires 2026-07-01.",
        "due_at": _days_from_now(7),
    },
    {
        "title": "Verify HELIX-1822 SSRF fix timeline with Yui",
        "body": "HELIX-1822 (webhook-router private IP blocking) is accepted risk expiring 2026-08-01. Confirm it's on Yui's sprint radar for Q3. If not, flag to Priya.",
        "due_at": _days_from_now(14),
    },
    {
        "title": "Get annual Stripe SOC 2 Type II report from vendor management",
        "body": "SOC 2 control CC9.2 requires annual review of Stripe's SOC 2 report. Last review was 2025-03. Raj Patel tracks vendor assessments — ask him for the current report or the date it's expected.",
        "due_at": _days_from_now(30),
    },
]


def seed_followups(dry_run: bool) -> None:
    from app.storage.followups_store import create, list_by_status
    existing_titles = {f["title"] for f in list_by_status("open", limit=500)}

    for fu in FOLLOWUPS:
        if fu["title"] in existing_titles:
            print(f"  [followup] '{fu['title'][:60]}' already exists — skipped")
            continue
        if not dry_run:
            create(
                title=fu["title"],
                body=fu.get("body"),
                due_at=fu.get("due_at"),
            )
        from datetime import datetime
        due = datetime.fromtimestamp(fu["due_at"]).strftime("%Y-%m-%d") if fu.get("due_at") else "no due date"
        print(f"  [followup] Created '{fu['title'][:65]}'  due={due}")


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be inserted without writing to the DB")
    args = parser.parse_args(argv)
    dry_run = args.dry_run

    if dry_run:
        print("=== DRY RUN — no changes will be written ===\n")

    # Force DB init before any store imports.
    from app.db import get_conn
    get_conn()

    sections = [
        ("Organization", seed_org),
        ("Teams", seed_teams),
        ("Projects", seed_projects),
        ("DFD Analyses", seed_dfds),
        ("Decisions", seed_decisions),
        ("Glossary", seed_glossary),
        ("Lessons", seed_lessons),
        ("Tabletop", seed_tabletop),
        ("Journal entries", seed_journal),
        ("Follow-ups", seed_followups),
    ]

    team_ids: dict[str, str] = {}
    for label, fn in sections:
        print(f"\n[{label}]")
        if label == "Teams":
            team_ids = fn(dry_run)
        elif label == "Projects":
            fn(team_ids, dry_run)
        else:
            fn(dry_run)

    print("\nDone." if not dry_run else "\nDry run complete — no changes written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
