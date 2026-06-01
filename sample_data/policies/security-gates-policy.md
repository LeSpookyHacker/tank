# Secure SDLC — Security Gates Policy

> Owner: AppSec · Status: Draft v1.0

Defines the security gates every MedScribe service must pass in CI before deploy
to `medscribe-prod`. Enforced via GitHub Actions (see the service repos'
`.github/workflows/`).

## Required gates

| Gate | Tool | Blocking? | Notes |
|---|---|---|---|
| SAST | Semgrep (+ custom MedScribe rules) | Yes on ERROR | PHI-in-logs, auth-missing, llm-output-handling |
| SCA / dependencies | `pip-audit` / `npm audit` + OSV | Yes on Critical/High | SLA per vuln-sla-policy |
| Secrets scan | gitleaks | Yes on any finding | Pre-commit + CI |
| Container scan | Trivy (Artifact Registry) | Yes on Critical | Base images pinned by digest |
| DAST | OWASP ZAP baseline | Warn (staging) | Auth + tenant-isolation tests for portals |
| IaC policy | Terraform + conftest | Yes | Cloud Run ingress must be internal-only |

## Exceptions

Any gate exception requires a logged decision (see the decisions log) with an
owner and an `expires_at`. Standing exceptions are reviewed monthly.

## Current state (program start)

None of these gates are enforced yet. Standing up SAST → secrets → SCA →
container → DAST (in that order) is the P2 workstream for the first 60 days.
