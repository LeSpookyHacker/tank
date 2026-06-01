# Regulatory Context — MedScribe-R-Us

> Owner: HIPAA Privacy Officer · Status: Reference

## Frameworks in scope

| Framework | Applicability | Status |
|---|---|---|
| HIPAA / HITECH | Primary — PHI, BAAs, breach notification | Ongoing obligation |
| SOC 2 Type II | Enterprise customer trust requirement | Audit window opens 2026-09-01 |
| HITRUST CSF | Common healthcare enterprise requirement | Target year 2 |
| OWASP LLM Top 10 | AI summarization pipeline risks | Adopted for AI threat model |
| NIST CSF 2.0 | Program framework alignment | Mapping in progress |

## HIPAA obligations as a Business Associate

- **BAA** with every covered entity (customer health system).
- **Breach notification** to covered entities without unreasonable delay and no
  later than 60 days after discovery (HITECH).
- **Minimum necessary** access to PHI — enforced via RBAC + ABAC (care-team).
- **Audit controls** (§164.312(b)) — tamper-evident audit_events.
- **Risk analysis** (§164.308(a)(1)(ii)(A)) — formal SRA owed; STRIDE register
  is the starting point.

## Breach-clock note

The HIPAA/HITECH discovery clock starts when the incident is **discovered**, not
when triage completes. IR runbooks must capture discovery time explicitly.

## Data residency

All PHI processing stays in US GCP regions (`us-central1` prod, `us-east1` DR).
No PHI leaves the VPC Service Controls perimeter except approved notes written to
the customer's own EMR.
