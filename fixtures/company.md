# Helix Robotics — company brief

> Fictional. For Tank demo use only.

## What we do

Helix Robotics provides payments and identity infrastructure specialized
for the robotics OEM market. Think of us as "Stripe + Auth0, narrowed
to industrial automation customers." OEMs integrate our SDKs into their
device fleets and customer portals; we handle the messy parts —
charging, identity federation, webhook fanout to their billing
systems.

## Numbers

- Founded 2021, HQ Austin, satellite offices in Seattle and Lisbon.
- ~80 employees, ~55 engineering.
- Series B closed Q3 2025 ($42M, led by Cascade Ventures).
- Customers: ~120 robotics OEMs, mostly North America + EU.
- Revenue: payments processing fees + per-seat identity SaaS.

## Stack

- Cloud: AWS, primary region `us-west-2`. Prod account
  `999988887777`, staging account `888877776666`.
- Compute: EKS for stateful services; Lambda for webhook fanout.
- Storage: RDS PostgreSQL, DynamoDB for device-registry, S3.
- Data warehouse: Snowflake (vendor: Snowflake Inc.).
- Secrets: HashiCorp Vault, self-hosted in-cluster.
- SSO: Okta (employees), customer-side: OAuth2/OIDC via our own
  identity-svc.
- Payments downstream: Stripe.
- Observability: Datadog, Sentry.
- Source: GitHub Enterprise Cloud.
- CI: GitHub Actions.
- IaC: Terraform Cloud.

## Internal domains

- `*.helix.internal` — internal services (set `TANK_INTERNAL_TLD=helix.internal`).
- `*.corp` — used by IT systems (HRIS, internal wiki, etc.).
- `helix.io` — customer-facing.
- `helixrobotics.com` — employee email + marketing.

## Security posture (as inherited)

- SOC 2 Type I attestation from 2024 Q4. Type II audit window opens
  September 2026 — first big external deadline.
- One previous security hire: Diana Okoro, joined Q1 2026 to build out
  Detection & Response. You're the second.
- No formal AppSec program. No formal threat modeling. No central
  vulnerability management. Snyk scans run on PRs but findings aren't
  triaged.
- IAM hygiene: Okta everywhere for employees; customer-facing OAuth
  is in identity-svc; AWS access is via SSO into a single tooling
  account, with cross-account assume-role into prod/staging. Some
  long-lived IAM users still exist for legacy CI integrations (this
  is on Raj's plate).
- Vault is healthy but adoption is uneven — most services use it, two
  don't (you'll find out which).

## Your scope (loose, to be refined during onboarding)

You're joining Priya Shah's Platform org as "Security Engineer." The
written JD says "AppSec-flavored, but expect to touch cloud and
detection partnership." Priya has hinted at three first-quarter
priorities, none yet committed:

1. Stand up a real vulnerability-management workflow on top of Snyk.
2. Audit IAM in the prod account, kill long-lived keys.
3. Build out a threat model for the payments path.

What's NOT in scope: GRC documentation (that's Tom's domain),
customer-facing trust collateral, compliance audit prep beyond what
overlaps with #1-3 above.

## First 5 people you should meet

(See `people/org-chart.md` for the full tree.)

1. **Priya Shah** — Director of Engineering, Platform. Your manager.
2. **Diana Okoro** — Detection & Response. The other security
   engineer. You'll partner closely.
3. **Marcus Chen** — Staff Engineer, Identity team. Owns the
   crown-jewel service (identity-svc).
4. **Alice Tanaka** — SRE Lead. Holds keys to most of prod, gatekeeps
   any prod changes you'll want to make.
5. **Raj Patel** — FinOps lead. Already trying to clean up IAM; ally,
   not adversary.
