# pii-vault — Service Architecture Detail

Service: **pii-vault**  
Team: Security  
Owner: (vacant — open: HELIX-2090)  
Hostname (prod): pii.helix.internal  
Language: Python  
Criticality: Tier-2 (critical — highest isolation tier)  
Last security review: 2025-11-20  

> **Warning**: pii-vault is the highest-risk service in the Helix estate.
> It is the sole store of customer billing addresses (Confidential tier).
> All changes require a security review before deployment.

---

## Overview

`pii-vault` is an isolated microservice that stores and retrieves customer
Personally Identifiable Information (PII) — specifically billing addresses
for OEM customers. It was carved out from `payments-api` in Q3 2024 after
HELIX-1750 identified that billing addresses were being replicated to the
analytics DB without masking.

Design constraints:
- **No internet egress** — egress rules block all outbound traffic except to
  the Vault endpoint and the DNS resolver.
- **Single authorized caller** — only `payments-api` may call `pii-vault`
  (enforced via mTLS client certificate CN check at the application layer).
- **No shared database** — isolated RDS instance (`pii-prod-pg`) in a
  dedicated VPC subnet with no cross-subnet routing to other RDS instances.
- **No direct admin shell** — SSH/ECS Exec disabled. Admin operations require
  a break-glass Vault policy (see below).

---

## Data stored

| Field | Classification | Notes |
| --- | --- | --- |
| `customer_id` (FK) | Internal | Reference to `payments-api` customer record |
| `billing_address_line1` | Confidential | |
| `billing_address_line2` | Confidential | |
| `city` | Confidential | |
| `state_province` | Confidential | |
| `postal_code` | Confidential | |
| `country_code` | Confidential | ISO 3166-1 alpha-2 |
| `created_at`, `updated_at` | Internal | |

No card PANs are stored here. PANs are tokenized by Stripe and never
reach Helix infrastructure.

---

## Authentication model

### Inbound (caller → pii-vault)

mTLS is the only accepted authentication mechanism:

1. `payments-api` holds a client certificate issued by Helix's internal CA
   (`vault://pki/issue/payments-api`). Rotated every 30 days.
2. `pii-vault` validates the client cert at the application layer, not just
   the TLS layer — it checks `CN=payments-api` and rejects all other CNs.
3. Additionally, a Vault-issued bearer token is required in the `X-Vault-Token`
   header. The token is scoped to `pii-vault/read` only.

If either mTLS or the bearer token fails, the request is rejected with 403.

### Outbound (pii-vault → RDS)

Dynamic credentials via Vault's database secrets engine:
- Role: `pii-vault-db-role` — `SELECT`, `INSERT`, `UPDATE`, `DELETE` on
  the `pii` schema only.
- Lease TTL: 1 hour. Renewed automatically while the process is running.
- **Uses IAM auth** — unlike identity-svc, pii-vault was migrated to RDS
  IAM authentication in Q4 2024. No static passwords.

---

## Break-glass access

Admin access (for incident response, schema migrations) follows a break-glass
process:

1. Request a break-glass Vault token via `vault write auth/approle/login`
   using the break-glass role (requires two-person approval in Vault).
2. The Vault token grants `pii-vault/admin` policy — allows read + write
   to RDS via a separate admin database role.
3. All break-glass access is audit-logged in Vault and shipped to Datadog.

**Known gap (HELIX-2095)**: Break-glass audit logs are shipped to Datadog
but there is no automated alert when break-glass access is used outside of
a declared incident window. A manual audit of Vault logs occurs monthly.
This should be automated.

---

## Data flow

```
payments-api (EKS pod)
  → [mTLS + Vault bearer token]
    → pii-vault (EKS pod, isolated node group)
      → Vault (credential check + audit log)
      → RDS pii-prod-pg (IAM auth)

Admin (break-glass only)
  → Vault (two-person approval)
    → pii-vault admin DB role
      → RDS pii-prod-pg
```

---

## Network isolation

- EKS node group: `ng-pii` — dedicated, not shared with other services.
- Security group `sg-pii-vault`:
  - Inbound: TCP 443 from `sg-payments-api` only.
  - Outbound: TCP 443 to Vault endpoint, TCP 5432 to `sg-pii-db`, UDP 53.
  - No inbound/outbound to internet gateway.
- RDS subnet group: `rds-pii-isolated` — no route to NAT gateway.

---

## Encryption

- **At rest**: RDS encrypted with Customer-Managed Key (CMK) in AWS KMS.
  Key alias: `alias/helix-pii-prod`. Key policy requires two IAM principals
  for administrative operations (key rotation, deletion).
- **In transit**: TLS 1.3 enforced on all connections.
- **KMS key rotation**: Annual automatic rotation (AWS-managed schedule).

---

## Threat surface — notes from Priya

1. **mTLS cert compromise on payments-api side** — if the payments-api mTLS
   cert is stolen (e.g., extracted from a running container), the attacker can
   impersonate payments-api to pii-vault. The Vault bearer token is a second
   factor but it's also available to the payments-api process. Severity: Critical.

2. **Break-glass without automated alerting (HELIX-2095)** — unauthorized
   break-glass access would only be noticed in the monthly manual audit.
   Window of undetected access: up to 30 days. Severity: High.

3. **Vault token exfiltration from pii-vault pod** — if a container escape
   occurs, the attacker could exfiltrate the Vault bearer token and read
   PII directly. No exec/shell access helps, but does not prevent read of
   environment variables from a compromised process. Severity: Critical.

4. **CMK key deletion** — if the KMS CMK is deleted (requires 7-30 day
   pending deletion window), RDS data becomes permanently unreadable. No
   CMK deletion alert exists. Severity: High.

5. **No rate limiting on pii-vault** — currently no rate limiting at the
   application level. A compromised payments-api could bulk-export all
   customer billing addresses. Consider rate limiting `GET /pii/*` per
   `customer_id`. Severity: High.

---

## API surface

| Endpoint | Purpose | Auth |
| --- | --- | --- |
| `GET /pii/{customer_id}` | Retrieve billing address | mTLS + Vault token |
| `PUT /pii/{customer_id}` | Create/update billing address | mTLS + Vault token |
| `DELETE /pii/{customer_id}` | Delete billing address (GDPR erasure) | mTLS + Vault token |
| `GET /health` | Health check | None (VPC-only) |

---

## On-call and escalation

- Primary rotation: platform-on-call (alice.tanaka@helixrobotics.com)
- Escalation: priya.shah@helixrobotics.com → tom.brandt@helixrobotics.com (CTO)
- For any confirmed data exposure: legal@helixrobotics.com must be notified
  within 1 hour (GDPR + OEM contract obligation).
- Runbook: `runbooks/respond-to-pii-breach.md`
