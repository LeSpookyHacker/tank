# PHI Data Flow — Lifecycle

> Owner: AppSec · Status: Draft v1.0
> Addresses T-004 (transcript tampering), T-005 (audit-log repudiation),
> T-007 (scrubbing gap), T-008 (cross-patient token leak), T-009 (approval bypass).

Traces every PHI category from entry to deletion. Primary reference for HIPAA
audit prep, IR investigations, and architecture review.

## PHI categories processed

Patient/clinician voice (biometric), patient name, DOB, dates of service,
geographic data, phone, email, MRN / account numbers, ICD-10 codes,
medications, treatment plans, SSN (rare).

## Lifecycle by stage

### Stage 1 — Audio capture
- GCS `gs://medscribe-phi-audio-{tenant_id}/{appointment_id}/{ts}.opus`,
  AES-256 + per-tenant CMEK (Cloud KMS).
- Write: `audio-ingest` SA only. Read: `transcription` SA only. No human access.
- Integrity (T-003): SHA-256 per segment, stored in MongoDB `recordings`,
  verified before transcription.
- Retention per BAA (default 7 yr). Deletion = CMEK key destroy + object delete.

### Stage 2 — Transcription
- MongoDB Atlas `transcripts` collection, field-level encryption on `content`
  and `speaker_segments`. Reachable only at `mongo-prod.medscribe.internal`.
- Write: `transcription` SA. Read: `phi-scrub`, `transcription`.
- Integrity (T-004): HMAC-SHA256 of content; append-only validator rule;
  modifications rejected at the DB layer and logged.

### Stage 3 — De-identification
- Output: zero PHI (HIPAA Safe Harbor, 45 CFR §164.514(b)).
- Token map in a **separate** `token_maps` collection, field-level encrypted on
  `value`. Never replicated externally, never sent to Vertex AI.
- Session binding (T-008): `session_id` = HMAC(appointment_id + patient_id +
  tenant_id). Re-injection verifies the binding; cross-patient substitution is
  architecturally impossible without breaking the HMAC.

### Stage 4 — AI summarization
- Only the de-identified transcript + system prompt cross the VPC Service
  Controls perimeter to Vertex AI (via `vertex-proxy.medscribe.internal`).
- Never crosses: raw transcript, token map, any identifier.
- Logging: metadata only (`session_id`, token counts, timestamp) — never content.

### Stage 5 — SOAP note (pre-approval)
- MongoDB `notes`: `{appointment_id, patient_id, tenant_id, content,
  status:"draft", approved_by:null}`.
- `approved_by` is write-protected: only the Note Approval endpoint
  (authenticated as the assigned clinician) may set it.
- Approval gate (T-009): EMR Integration validates `status=="approved" AND
  approved_by!=null` by reading MongoDB directly — never from the request payload.

### Stage 6 — EMR write-back
- FHIR patient binding (T-010): SMART token requested with
  `patient/{id} encounter/{id}` scope; `patient` claim validated against the
  appointment binding; FHIR response `subject` validated; mismatch halts + alerts.

### Stage 7 — Audit logging (T-005)
- Every PHI access → entry in append-only `audit_events`: `event_id, timestamp,
  actor_id, actor_role, tenant_id, action, resource_type, resource_id,
  patient_id (SHA-256 hashed), outcome, hmac`.
- `phi-audit-writer` SA has INSERT-only. Logs mirrored to GCP Cloud Logging
  (immutable). HMAC chain breaks on tamper. Retention ≥ 6 yr.

## Deletion sequence
1. CMEK key destroy (cryptographic erasure of GCS audio).
2. GCS object delete confirmed.
3. MongoDB delete (`transcripts`, `notes`, `token_maps`).
4. Deletion event to audit log (the audit entry itself is retained).
5. Customer notified with confirmation timestamp.
