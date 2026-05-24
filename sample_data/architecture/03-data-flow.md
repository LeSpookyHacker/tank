# Data flow — what data lives where

## Data classifications (per `policies/data-classification.md`)

| Tier | Examples | Storage rules |
| --- | --- | --- |
| **Restricted** | Card PANs, full SSNs, customer JWT signing keys | Never stored. Tokenized via Stripe (cards) or held in Vault (keys). |
| **Confidential** | Customer billing addresses, OEM contract terms, device serial numbers | Encrypted at rest with customer-managed keys (CMK). Access logged. |
| **Internal** | Employee emails, internal hostnames, source code | Encrypted at rest with AWS-managed keys. Restricted to VPN/SSO. |
| **Public** | Marketing content, public API docs | No restrictions. |

## Service → data map

| Service | Data tiers it touches | Stores |
| --- | --- | --- |
| identity-svc | Confidential (user PII), Restricted (JWT keys via Vault) | RDS PostgreSQL `identity-prod-pg`, Vault, Redis |
| payments-api | Confidential (billing addresses indirectly via pii-vault), Restricted (Stripe restricted keys via Vault) | RDS PostgreSQL `payments-prod-pg`, Vault |
| pii-vault | Confidential (billing addresses) | RDS PostgreSQL `pii-prod-pg` (CMK-encrypted, isolated subnet) |
| orders-api | Confidential (OEM contract terms) | RDS PostgreSQL `orders-prod-pg` |
| webhook-router | Internal (event metadata) | DynamoDB `helix-webhook-events` |
| device-registry | Confidential (device serials), Restricted (device cert private keys via Vault) | DynamoDB `helix-devices`, Vault |
| dashboard-web | (proxies; stateless) | None directly |
| analytics-pipeline | Confidential (masked at dbt layer) | Snowflake `HELIX_PROD` warehouse |

## Replicas + analytics path

```
RDS primary (prod)
    ↓ logical replication (slot per database)
RDS read-replica (analytics-only)
    ↓ dbt extract via assume-role into analytics account 888877776666
S3 staging bucket arn:aws:s3:::helix-prod-analytics-staging
    ↓ Snowpipe
Snowflake HELIX_PROD warehouse
```

Snowflake account: `cortex-eq39172`.

PII masking happens in the dbt layer, not at extract time — this is a
**known weakness** (open issue HELIX-2031). If the dbt layer ever
errors silently and lets a model materialize without masking, Snowflake
ends up with cleartext billing addresses. We have a dbt test that
should catch this, but it hasn't been audited recently.

## Backup + retention

- RDS automated backups: 35 days for prod, 7 days for staging.
- S3 lifecycle: hot 90 days → Glacier 1 year → delete (varies per
  bucket; see `runbooks/s3-lifecycle.md` — DRAFT, never finished).
- Snowflake time-travel: 7 days.
- Vault audit logs: shipped to Datadog and S3, retained 1 year.

## Cross-region

We run prod entirely in `us-west-2`. Disaster-recovery for RDS is
cross-region snapshot replication to `us-east-1` once daily. There
is no warm-standby; RTO is "best effort" (we have not tested it).
This is a known concentration risk.

Customer-facing latency for EU customers comes through CloudFront +
ALB → still hits us-west-2 origin. Vercel handles the edge for
dashboard-web; the backend round-trip from EU adds ~150ms baseline.
There's no GDPR-specific data residency requirement today (no
contracts mandate it), but customer #44 (Lisbon) asked about it
last month — open in HELIX-2104.

## Sensitive paths to threat-model

(Notes from Priya for the new security hire.)

1. **payments-api → pii-vault** — only path that crosses tier-2 →
   tier-2 with restricted data. Auth is mTLS + a Vault-issued bearer
   token. Either link compromised = customer billing-address
   exfiltration.
2. **identity-svc → RDS identity-prod-pg** — credentials sit in Vault
   but RDS itself only has IAM authentication enabled for IAM users,
   not for the application principal (it uses password auth via Vault
   dynamic secrets). Worth a look.
3. **analytics-pipeline assume-role into prod** — the dbt service has
   read access to RDS replicas of every prod DB. Any compromise of
   the analytics account gets a wide read of customer data.
4. **webhook-router → customer URLs** — outbound SSRF surface. We
   restrict to HTTPS but don't deny private IP ranges (HELIX-1822).
   A malicious customer could trick our router into hitting our own
   internal endpoints.
