# Data Classification Policy — MedScribe-R-Us

> Owner: HIPAA Privacy Officer + AppSec · Status: Draft v1.0

Every data element at MedScribe-R-Us is assigned one of four tiers. Handling,
encryption, access, and retention requirements follow from the tier.

## Tiers

### Tier 1 — PHI / Restricted
Protected Health Information: audio, raw transcripts, SOAP notes, token maps,
MRNs, patient identifiers.
- **Encryption:** AES-256 at rest; CMEK for audio; field-level for transcripts;
  TLS 1.3 / mTLS in transit.
- **Access:** least-privilege service accounts only; no human standing access;
  break-glass with full audit.
- **Logging:** content NEVER logged; identifiers logged hashed only.
- **Retention:** per customer BAA, default 7 years; cryptographic erasure on delete.
- **Cross-boundary:** never crosses to Vertex AI; only de-identified text does.

### Tier 2 — Confidential
De-identified transcripts, aggregate analytics, internal architecture docs,
security findings.
- Encryption at rest + in transit; access limited to employees with need-to-know.

### Tier 3 — Internal
Non-secret runtime config, CMDB, on-call schedules, runbooks.
- Standard encryption; access limited to staff.

### Tier 4 — Public
Marketing site, public API docs.
- No special handling.

## Secrets handling

Secrets (Vertex AI key, MongoDB connection string, FHIR OAuth client secret,
Datadog API key, Auth0 client secret) are Tier 1 by blast radius. They live ONLY
in GCP Secret Manager, are accessed via Workload Identity with per-secret
conditions, rotate on schedule (90d API keys / 180d OAuth secrets), and must
never appear in code, env files, logs, or tickets.

## De-identification standard

PHI is de-identified per HIPAA Safe Harbor (45 CFR §164.514(b)) before any LLM
processing. The scrubber must be validated against a labeled PHI corpus; any
false negative is a reportable de-identification failure (see T-007).
