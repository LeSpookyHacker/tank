# Postmortem — Speech-to-Text Cost Spike / Partial DoS

> Date: 2026-03-19 · Severity: SEV-3 · Status: published
> Relates to T-012

## Summary
A buggy mobile client retried failed audio uploads in a tight loop, submitting
the same 45-minute recording ~600 times in an hour. Audio Ingestion accepted all
of them; Transcription pushed each to Speech-to-Text. STT spend for the day was
~22× normal and the transcription queue backed up, delaying real notes by ~25 min.

## Impact
Availability degradation (delayed notes during a clinic afternoon) + unexpected
GCP spend. No PHI impact.

## Timeline
- 14:02 — client bug ships; retry loop begins for one clinician.
- 14:40 — on-call notices STT spend + queue depth alarms.
- 15:05 — offending client + appointment identified; uploads blocked at gateway.

## Root cause
No per-tenant / per-appointment rate limit or dedup on audio ingestion; no
file-size/duration cap enforced at the gateway.

## Action items
1. Enforce max duration + size and per-appointment dedup at API Gateway. (owner: Platform)
2. Per-tenant STT spend quota + Datadog alert. (owner: Platform)
3. Idempotency key on audio upload. (owner: Pipeline)

## Lessons
- Cost is an availability control in usage-metered AI pipelines; bound it.
