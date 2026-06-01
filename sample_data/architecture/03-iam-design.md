# IAM Design — MedScribe-R-Us

> Owner: AppSec · Status: Draft v1.0
> Addresses T-001 (credential spoofing), T-011 (privilege escalation),
> T-013 (Secret Manager compromise).

Layered identity model: RBAC for coarse permissions + ABAC for clinical-context
enforcement (HIPAA "minimum necessary").

## Identity providers

| User type | IdP | Protocol | MFA |
|---|---|---|---|
| Clinicians | Health-system IdP (Epic/Cerner SSO) | OIDC / SAML 2.0 | Enforced by health system |
| Patients | MedScribe Auth (Auth0) | OAuth 2.0 PKCE | Optional (magic link) |
| Clinic Admins | MedScribe Auth (Auth0) | OAuth 2.0 PKCE | Required (TOTP / WebAuthn; no SMS) |
| Platform Admins | Auth0 + hardware key | OAuth 2.0 PKCE | Required — FIDO2 only |
| Internal services | GCP Workload Identity | SA federation | mTLS |

## RBAC roles

`clinician` (own + care-team patients), `patient` (own records, read-only),
`clinic_admin` (their `tenant_id` only), `platform_admin` (all tenants, audited),
`integration_partner` (FHIR scope), `service_account` (per-service GCP IAM).

### JWT claims
```json
{ "sub":"user_uuid", "role":"clinician", "tenant_id":"health_system_uuid",
  "npi":"1234567890", "iss":"https://auth.medscribe.internal",
  "aud":"medscribe-api", "exp":1700000900, "jti":"unique_token_id" }
```
`tenant_id` is ALWAYS set server-side from the verified IdP claim — never from the
request payload/path/query. This is the primary control for T-011.

## ABAC — clinical context

> A clinician may access a patient's data only if an active care-team
> relationship exists for the encounter being accessed.

The ABAC service caches FHIR `CareTeam` memberships (5-min TTL), logs every
allow/deny, and is **fail-closed**: if unavailable, access is denied.

## Session management

| Parameter | Value |
|---|---|
| Access token lifetime | 15 min |
| Refresh token lifetime | 8 h (clinician) / 4 h (admin) |
| Refresh rotation | on every use |
| Session binding | IP + User-Agent fingerprint |
| Concurrent sessions | 3 per user |
| Anomalous login | geography + device → step-up TOTP |

## Service-to-service identity (GCP Workload Identity)

No SA key files on disk. Each Cloud Run service has a dedicated SA with least
privilege:

| Service | Service account | Permissions |
|---|---|---|
| Audio Ingestion | `audio-ingest@medscribe-prod.iam` | GCS write (audio bucket only) |
| Transcription | `transcription@medscribe-prod.iam` | GCS read, STT API, Secret Manager (STT key) |
| PHI Scrubbing | `phi-scrub@medscribe-prod.iam` | MongoDB read (transcripts) |
| AI Summarization | `ai-summary@medscribe-prod.iam` | Vertex AI, Secret Manager (Vertex key) |
| Output Validation | `output-val@medscribe-prod.iam` | MongoDB write (notes) |
| EMR Integration | `emr-integration@medscribe-prod.iam` | MongoDB read (approved notes), Secret Manager (FHIR OAuth) |

**Target state:** no SA holds `roles/secretmanager.admin` or any wildcard role.
See `iam/gcp-iam-bindings.json` for the intended least-privilege bindings and
`iam/overbroad-role.json` for a discovered over-broad binding pending remediation.
