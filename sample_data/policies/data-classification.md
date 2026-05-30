# Data Classification

**Owner:** Tom Brandt
**Effective:** 2025-08-01

## Tiers

### Restricted

Examples: card PANs, full SSNs, customer JWT signing keys, internal
CA private keys, AWS root credentials.

Storage rules:

- **Never** stored in our systems. Tokenize through a third party
  (Stripe for cards) or hold in HashiCorp Vault (cryptographic keys).
- Vault paths storing Restricted data must use the
  `transit` secrets engine with derivation enabled. KV engine is
  not acceptable for Restricted.
- Access to Restricted data must be just-in-time, max 4 hours,
  with reason logged.

### Confidential

Examples: customer billing addresses, OEM contract terms, device
serial numbers, identity-svc PostgreSQL data, employee compensation.

Storage rules:

- Encrypted at rest with customer-managed keys (KMS CMK).
- Access logged to the audit account.
- Multi-tenant isolation enforced at the application layer via
  `customer_id` scoping (no shared-DB queries that span tenants).
- Replication outside `us-west-2` requires customer consent (we have
  blanket consent in our standard CMA, but EU customers may have
  data residency carve-outs — see HELIX-2104).

### Internal

Examples: employee emails, internal hostnames, source code, CI logs,
Datadog dashboards.

Storage rules:

- Encrypted at rest with AWS-managed keys.
- Restricted to authenticated employees via SSO.
- May be shared with vendors under NDA.

### Public

Examples: marketing content, public API docs, open-source
contributions, customer-facing status page.

No storage restrictions.

## Movement between tiers

- **Restricted → anywhere**: prohibited. Always tokenize.
- **Confidential → Internal**: requires irreversible redaction
  (e.g., hashing, masking).
- **Internal → Public**: requires Tom's approval and legal review.

## Where this policy is enforced

- pii-vault uses CMK encryption (Confidential).
- Snowflake dbt models mask Confidential PII at extract time
  — see HELIX-2031 for the known weakness here.
- S3 buckets containing Confidential data have bucket-policy
  conditions requiring `aws:SecureTransport=true` and CMK encryption.
- Datadog log scrubbing rules redact common Confidential patterns
  (emails, SSN-shaped strings). Audit drift quarterly.

## Open work

- The `analytics-pipeline` masking weakness (HELIX-2031) is the
  most pressing one. A dbt test should catch unmasked PII but
  hasn't been audited in 6+ months.
- We have no automated detection for `Restricted` data ending up in
  the wrong place — would be a great addition once you start.
