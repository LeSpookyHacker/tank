# payments-api

Charges + refunds for Helix Robotics customers. Stripe lives downstream;
we never see card data ourselves.

**Owner:** Sam Liu (sam.liu@helixrobotics.com)
**Team:** Payments
**On-call rotation:** Payments on-call (PagerDuty service
`payments-api-prod`)
**Tier:** 0 (customer-facing critical path)
**Repo:** `github.com/helix-robotics/payments-api`

## Quickstart (local)

```bash
poetry install
docker compose up -d postgres redis
poetry run alembic upgrade head
poetry run uvicorn payments_api.main:app --reload --port 8080
```

A working dev environment requires a Stripe test API key (load it from
`.env`) and a local Vault dev server at `http://127.0.0.1:8200`. The
team's onboarding doc has the full local-stack instructions —
`https://helix.notion.site/Payments-Onboarding-...`.

## Production

- ECR image: `999988887777.dkr.ecr.us-west-2.amazonaws.com/payments-api`
- EKS namespace: `payments-prod`, 6 replicas
- ALB DNS: `payments.helix.io` (customer) and
  `payments.helix.internal` (intra-cluster)
- Database: RDS PostgreSQL `payments-prod-pg` in
  account `999988887777`
- Secrets: HashiCorp Vault at `vault.helix.internal`, path
  `secret/payments-api/prod/*` (Stripe restricted keys, DB password)

## Architecture

- FastAPI app, async throughout.
- Postgres for charge ledger.
- Stripe SDK for downstream PSP.
- Vault Agent sidecar issues mTLS cert + Vault token at pod start.
- Reads `pii-vault` for billing-address details (mTLS + bearer token).
- Identity-svc verifies JWT signatures via JWKS (cached 4 hours).

## Critical endpoints

| Endpoint | Purpose | Auth |
| --- | --- | --- |
| `POST /charges` | Create a charge | Customer JWT, scope `charges:write` |
| `GET /charges/{id}` | Read a charge | Customer JWT, scope `charges:read` |
| `POST /charges/{id}/refund` | Refund | Customer JWT, scope `charges:write` |
| `GET /healthz` | Liveness | none |

## Auth flow

We do not authenticate end-users ourselves. The customer's OEM portal
talks to identity-svc, gets an access token, and forwards it as a
Bearer header to us. We verify:

1. JWT signature against identity-svc's published JWKS.
2. `aud` includes `payments-api`.
3. `scope` includes the required scope for the operation.
4. `customer_id` matches the resource being accessed (multi-tenant
   isolation).

See `src/payments_api/auth.py`.

## Deployment

GitHub Actions workflow `.github/workflows/ci.yml` runs tests on PRs.
Merges to `main` build + push to ECR; `helmfile-deploy` workflow
(in a separate repo) does the EKS rollout. We deploy via Argo CD,
not from CI directly.

## Open issues (for the new security hire)

- HELIX-1822 — `webhook-router` egress doesn't deny private IPs.
  Not strictly in our scope but the downstream impact lands on us
  if SSRF lets an attacker hit `pii.helix.internal`.
- HELIX-1981 — request/response logging includes the full JWT in
  some error paths. Should be redacted.
- No threat model on file. Priya's #1 ask is to build one.
