# Access Policy

**Document owner:** Tom Brandt (CTO)
**Effective:** 2025-09-01 (last revised 2026-02-14)
**Approval cadence:** annual; next review 2026-09-01.

> This markdown file is the source-of-truth. The DOCX rendering used
> by the People team for HR onboarding is generated from this file by
> `scripts/_gen_fixtures.py`.

## Scope

This policy applies to all production and confidential-tier systems
operated by Helix Robotics. "Production" means anything in account
`999988887777` or the `helix.io` domain.

## Identity

- **Employees** authenticate to all systems via Okta SSO. No local
  passwords for service consoles. Okta MFA is required at every
  login (no remember-me beyond 8 hours).
- **Customer end-users** authenticate via `identity-svc`'s OAuth2/OIDC
  flow.
- **Service-to-service** authentication is mTLS within the prod VPC,
  with workload identities issued by HashiCorp Vault via the
  Kubernetes auth method.

## Authorization principles

1. **Least privilege**: roles grant only what's needed for the
   advertised purpose. Default-deny.
2. **Just-in-time elevation**: privileged access (e.g., prod admin)
   is requested via the Just-In-Time tool, time-boxed to 4 hours,
   and logged in Datadog.
3. **No long-lived access keys for humans**: humans use SSO into AWS
   Identity Center. The two remaining IAM users
   (`iam-user/ci-snyk`, `iam-user/legacy-jenkins`) are tracked in
   HELIX-1879 for removal.
4. **No shared accounts**: each human has a unique identity.

## Roles (AWS Identity Center permission sets)

| Role | Granted to | Allowed accounts |
| --- | --- | --- |
| AdministratorAccess | Tom Brandt, Alice Tanaka (break-glass) | all |
| PlatformEngineer | Marcus Chen, Yui Tanaka, Alice Tanaka | prod, staging, tooling |
| ReadOnly | every engineer | all |
| FinOpsReadWrite | Raj Patel | all (cost-explorer scoped) |
| Security | Mei Watanabe (first security hire) | all |
| Auditor | external audit firm during attestation window | tooling + security only |

Break-glass admin use is logged to the security S3 bucket
`arn:aws:s3:::helix-security-audit-logs` in account `666655554444`
and alerted to `#security-alerts` within 5 minutes.

## Customer access

- Customers manage their own users via SCIM or our dashboard-web UI.
- Customer JWTs expire after 1 hour; refresh tokens after 30 days
  (rotated on use).
- Customers may not view other customers' data; multi-tenant
  isolation is enforced at the `customer_id` claim layer in
  payments-api and orders-api.

## Vendor access

External vendors (e.g., Snowflake) authenticate via SAML federation
where supported, or via dedicated IAM users in `helix-tooling`
account with monthly key rotation. No vendor user has access to
`helix-prod`.

## Review cadence

- Quarterly access review: Tom + Priya audit role assignments and
  break-glass usage.
- Monthly key rotation: any long-lived credentials are rotated.
- On termination: Okta deactivation triggers automatic AWS Identity
  Center revocation within 5 minutes.

## Exceptions

Exceptions to this policy must be filed in HELIX-EXCEPTIONS Jira
project, time-boxed (max 90 days), and approved by Priya (technical)
+ Tom (business).
