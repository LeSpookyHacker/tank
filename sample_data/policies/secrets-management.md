# Secrets Management Policy

**Policy ID**: SEC-POL-003  
**Owner**: Unowned — interim-held by Tom Brandt (CTO, tom.brandt@helixrobotics.com); transfers to the incoming first security hire within first 30 days  
**Approved by**: tom.brandt@helixrobotics.com  
**Effective date**: 2025-09-01  
**Review cycle**: Annual  
**Status**: Active

---

## Purpose

Define how Helix Robotics stores, rotates, and distributes secrets (API keys,
database credentials, TLS certificates, encryption keys) to minimize the risk
of unauthorized access to production systems and customer data.

---

## Scope

Applies to all engineering teams building, operating, or integrating with Helix
production systems. Covers: AWS IAM credentials, database credentials, API keys,
service-to-service shared secrets, TLS/mTLS certificates, and encryption keys.

Does **not** cover: end-user passwords (managed by Okta), customer-provided
webhook secrets (encrypted at rest per HELIX-1802), or secrets held by
third-party vendors in their own systems.

---

## Requirements

### 1. All production secrets must be dynamic where possible

Services **must** use HashiCorp Vault's dynamic secrets engine for:

- RDS/PostgreSQL credentials (Vault database secrets engine)
- AWS IAM credentials (Vault AWS secrets engine)
- TLS certificates (Vault PKI secrets engine)

Dynamic secrets have short TTLs (maximum 8 hours) and are never stored in
source code, CI/CD environment variables, or application configuration files.

### 2. Static secrets require approval

Where dynamic secrets are not technically feasible, a static secret may be used
with explicit approval:

1. File a Jira ticket tagged `security-exception`.
2. Security team reviews and approves within 5 business days.
3. The static secret must be stored in Vault (`secret/static/<service>/<name>`)
   with rotation on a schedule no longer than 90 days.
4. The exception and rotation schedule are tracked in the Secrets Inventory
   (Vault path: `secret/meta/inventory`).

### 3. Rotation SLA

| Secret type | Maximum TTL |
| --- | --- |
| Database credentials (dynamic) | 8 hours |
| AWS IAM credentials (dynamic) | 1 hour |
| TLS certificates (PKI) | 30 days |
| Approved static API keys | 90 days |
| Encryption keys (KMS CMK) | 1 year (AWS-managed) |
| mTLS client certificates | 30 days |

### 4. Secret injection

Secrets must be injected at runtime using one of:

- **Vault Agent sidecar** — recommended for EKS workloads. Writes secrets to
  a tmpfs volume; process reads from file, not environment variable.
- **Vault SDK / API call** — for services with complex secret dependencies.
- **AWS Parameter Store (SecureString)** — acceptable for non-critical config
  where Vault integration is blocked (requires security team approval).

Secrets **must not** be injected via:
- Environment variables (visible in `kubectl describe pod` output)
- Docker build arguments
- CI/CD plaintext configuration

### 5. Secret detection in CI/CD

All git repositories must have `detect-secrets` pre-commit hooks enabled.
The CI pipeline runs `detect-secrets scan` on every pull request. Builds that
fail the scan cannot be merged.

Security scans run against the default baseline at `.secrets.baseline` in each
repo.

---

## Exemptions and known gaps

The following exemptions are currently open. Each has a Jira ticket and an
expiry date:

| Service | Exemption | Jira | Expires |
| --- | --- | --- | --- |
| analytics-pipeline | Snowflake connector uses static user/password (Vault integration not yet supported by connector) | HELIX-2031 | 2026-09-01 |

**HELIX-2031 context**: The Snowflake Python connector does not support dynamic
credential injection via Vault's database secrets engine. The static credential
is stored in Vault (`secret/static/analytics-pipeline/snowflake`) with a 90-day
rotation schedule. Risk: if the analytics account is compromised, the Snowflake
credential provides read access to `HELIX_PROD` warehouse. Mitigated partially
by Snowflake network policies restricting access to Helix's AWS Elastic IPs.

---

## Enforcement

- CI/CD secret scan failure blocks merge.
- Quarterly Vault audit (by security team) checks for static secrets missing
  from the Secrets Inventory.
- Any secret found committed to git triggers an immediate incident (P1) —
  see `runbooks/rotate-customer-api-key.md` for the rotation procedure.

---

## Contacts

| Role | Contact |
| --- | --- |
| Policy owner | unowned (interim: tom.brandt@helixrobotics.com → incoming security hire) |
| Vault admin | alice.tanaka@helixrobotics.com (SRE) |
| Escalation | tom.brandt@helixrobotics.com |
