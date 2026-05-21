# AWS account + region map

## Accounts

| Account ID | Name | Purpose | Owner |
| --- | --- | --- | --- |
| `999988887777` | `helix-prod` | Customer-facing prod | Alice Tanaka |
| `888877776666` | `helix-staging` | Pre-prod, analytics, dev/test | Yui Hayashi |
| `777766665555` | `helix-tooling` | SSO landing, CI runners, central logs | Raj Patel |
| `666655554444` | `helix-security` | Security tooling, log archive | (you, eventually) |
| `555544443333` | `helix-sandbox` | Per-engineer playgrounds | (free for all) |

All accounts live under a single AWS Organization. Org master is the
tooling account (`777766665555`). SCPs are applied at the OU level —
prod and staging share a tighter set than sandbox.

## SSO

Single Okta tenant fronts all accounts via AWS Identity Center (was
SSO). Users assume role into accounts; no long-lived IAM users for
humans (target state — see "Legacy IAM" below for what's still around).

Permission sets:

- `AdministratorAccess` — Tom, Alice (break-glass; logged)
- `PlatformEngineer` — Marcus, Yui, Alice
- `ReadOnly` — every employee in the engineering group
- `FinOpsReadWrite` — Raj
- `Security` — Diana, you
- `Auditor` — external audit firm during compliance windows

## Region layout

- **`us-west-2`** — primary, all prod workloads.
- **`us-east-1`** — DR snapshots only; no live compute.
- **`eu-central-1`** — empty today; provisioned for future EU
  workloads if HELIX-2104 (customer ask) leads to a data-residency
  commitment.

## VPC ranges

| Account | VPC | CIDR |
| --- | --- | --- |
| `helix-prod` | `prod-vpc` (`us-west-2`) | `10.50.0.0/16` |
| `helix-prod` | `dr-vpc` (`us-east-1`) | `10.60.0.0/16` (empty) |
| `helix-staging` | `staging-vpc` | `10.51.0.0/16` |
| `helix-tooling` | `tooling-vpc` | `10.52.0.0/16` |
| `helix-security` | `security-vpc` | `10.53.0.0/16` |

Egress NAT IPs (prod) live in `10.50.250.0/24` (publicly addressable
EIPs `52.27.x.x` range — three EIPs, publish to customer allowlists).

## Internal hostnames

| Hostname | Maps to | Notes |
| --- | --- | --- |
| `identity.helix.internal` | identity-svc ALB (private) | mTLS required |
| `payments.helix.internal` | payments-api ALB (private) | mTLS required |
| `orders.helix.internal` | orders-api ALB (private) | mTLS required |
| `webhooks.helix.internal` | webhook-router (no ingress, name resolves for metrics) | — |
| `devices.helix.internal` | device-registry ALB (private) | mTLS required |
| `pii.helix.internal` | pii-vault ALB (private) | mTLS + Vault token |
| `vault.helix.internal` | Vault cluster (3 nodes) | mTLS + Vault token |
| `ca.helix.internal` | internal CA service | mTLS |

## Legacy IAM (kill list)

These are the long-lived IAM users that still exist. Goal: zero by
end of Q3 2026.

- `iam-user/ci-snyk` — used by Snyk SaaS to pull scan results.
  Rotated 2025-11. Long-lived access key, scope: read-only on
  CodeArtifact. Plan: replace with OIDC trust to GitHub Actions
  (HELIX-1879).
- `iam-user/legacy-jenkins` — leftover from pre-GHA days. Should
  be deletable; need to verify nothing still uses it.

There are no other long-lived human users. Service-account-style IAM
users are not allowed by SCP except in the `helix-tooling` account.
