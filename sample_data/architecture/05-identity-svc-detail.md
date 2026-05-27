# identity-svc — Service Architecture Detail

Service: **identity-svc**  
Team: Identity  
Owner: marcus.chen@helixrobotics.com  
Hostname (prod): auth.helix.io  
Language: Go  
Criticality: Tier-0 (critical)  
Last security review: 2026-01-12

---

## Overview

`identity-svc` is the authentication and authorization backbone for all Helix
Robotics services. It implements:

- **OIDC Provider** — issues ID tokens and access tokens for OEM portal users
  (`app.helix.io`) and internal service-to-service auth.
- **OAuth2 Authorization Server** — authorization code flow (PKCE required),
  client credentials flow for M2M.
- **Session management** — Redis-backed session store; 15-minute access tokens,
  7-day refresh tokens.
- **MFA enforcement** — Okta as the upstream IdP; TOTP fallback for break-glass
  scenarios.

All other services (`payments-api`, `orders-api`, `pii-vault`, etc.) validate
JWTs issued by `identity-svc` by fetching the JWKS endpoint:
`https://auth.helix.io/.well-known/jwks.json`.

---

## Token signing

- **Algorithm**: RS256 (asymmetric). Private signing key is stored in HashiCorp
  Vault (`pki/sign/identity-jwt`), never written to disk.
- **Key rotation**: 90-day automatic rotation via Vault's PKI secrets engine.
  The `/.well-known/jwks.json` endpoint serves all active keys (current +
  previous rotation) to allow in-flight tokens to validate.
- **Known gap**: JWKS cache at consumer services is set to a 5-minute TTL. A
  compromised key cannot be revoked faster than 5 minutes without a coordinated
  roll of all consumers. No emergency revocation runbook exists (open: HELIX-2110).

---

## Data stores

| Store | Purpose | Auth mechanism |
| --- | --- | --- |
| RDS PostgreSQL `identity-prod-pg` (us-west-2) | User records, OAuth2 clients, refresh token index | Password auth via Vault dynamic secrets — **NOT IAM auth** (open: HELIX-2108) |
| Redis (ElastiCache) | Session tokens, rate-limit counters | No auth (VPC-private, security group restricted) |
| Vault | JWT signing key, RDS credentials, audit logs | Kubernetes ServiceAccount JWT (IRSA) |

**HELIX-2108 context**: The RDS instance was provisioned before IRSA was fully
adopted. Migrating to IAM auth requires a maintenance window. Deferred to Q2 2026.
Risk: if Vault is unavailable, identity-svc cannot rotate credentials and falls
back to a locally-cached password with a 24-hour TTL.

---

## Call graph

```
End user (browser)
  → CloudFront / ALB (TLS termination)
    → identity-svc (Go, EKS pod)
      → PostgreSQL identity-prod-pg (dynamic creds via Vault)
      → Redis (session store)
      → Vault (JWT signing, credential rotation)
      → Okta (OIDC federation for SSO login)

OEM device (M2M)
  → identity-svc /oauth2/token (client_credentials)
    → PostgreSQL (client lookup)
    → Vault (JWT signing)
```

---

## API surface

| Endpoint | Purpose | Auth required |
| --- | --- | --- |
| `POST /oauth2/authorize` | Authorization code flow initiation | None (redirect) |
| `POST /oauth2/token` | Token exchange (auth code, refresh, client credentials) | Client secret or PKCE verifier |
| `POST /oauth2/introspect` | Token validation for services | Bearer (service account) |
| `POST /oauth2/revoke` | Refresh token revocation | Bearer |
| `GET /.well-known/jwks.json` | Public JWKS for JWT validation | None |
| `GET /.well-known/openid-configuration` | OIDC discovery document | None |
| `GET /admin/users` | Internal admin (MFA-gated) | Bearer + admin scope |
| `GET /admin/clients` | OAuth2 client management | Bearer + admin scope |

The `/admin/*` endpoints are restricted to VPN CIDR `10.0.0.0/8` at the ALB
level (WAF rule). They require a token with `scope=helix:admin`.

---

## Rate limiting

- `/oauth2/token`: 20 requests/min per IP (sliding window, Redis-backed).
- `/oauth2/authorize`: 10 requests/min per `client_id`.
- No rate limiting on `/oauth2/introspect` — consumers hit this on every
  inbound request. Consider caching at consumer side (see HELIX-2112).

---

## Suspicious-login integration

A Sigma rule (`detections/helix-suspicious-login.yml`) watches for Okta login
events from countries outside US/Portugal. When triggered, Datadog alerts the
platform-on-call rotation.

`identity-svc` does not currently write structured auth events to a central
SIEM. Auth events go to CloudWatch Logs → forwarded to Datadog via Firehose.
Log format is not Sigma-compatible (open: HELIX-2115).

---

## Threat surface — notes from Priya

1. **JWT replay via long-TTL refresh tokens** — 7-day refresh tokens are a wide
   window if a token is stolen from a mobile device. No device-binding on
   refresh tokens. Severity: High.

2. **JWKS cache staleness during key compromise** — if a signing key is
   compromised, the 5-minute JWKS cache means consumers will accept forged
   tokens for up to 5 minutes after key revocation. No revocation mechanism
   exists. Severity: Critical.

3. **RDS password auth (HELIX-2108)** — Vault dynamic secrets mitigate most of
   this risk, but the fallback cached password is a concern. If Vault is
   unreachable for >24 hours, the cached cred is still valid. Severity: High.

4. **Redis unauthenticated** — Redis is VPC-private with SGs. A container escape
   or internal pivot can reach it without credentials. Session token theft would
   be invisible in current logs. Severity: Medium.

5. **Client secret storage** — OAuth2 client secrets are stored as bcrypt hashes
   in PostgreSQL. The hashing work factor is bcrypt-12, acceptable. However,
   there is no rotation schedule for client secrets (open: HELIX-2113). Severity: Low.

---

## On-call and escalation

- Primary rotation: platform-on-call (alice.tanaka@helixrobotics.com primary)
- Secondary: marcus.chen@helixrobotics.com
- Escalation: priya.shah@helixrobotics.com (Dir. Engineering)
- Runbook: `runbooks/investigate-suspicious-login.md`
- SLA: P0 response < 15 minutes, P1 < 1 hour
