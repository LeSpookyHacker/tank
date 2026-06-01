# Postmortem — PHI in Application Logs (Near-Miss)

> Date: 2026-05-12 · Severity: SEV-2 (near-miss) · Status: published
> Relates to T-006

## Summary
A debug log statement in the transcription-svc exception handler logged the full
request body — including a raw transcript fragment containing PHI — to Datadog.
Caught during a manual log review, not by tooling. ~40 log lines across ~2 hours
contained PHI before the line was reverted. Datadog has no PHI BAA.

## Impact
Potential PHI disclosure to a log platform without a BAA. No evidence of external
access. Privacy Officer assessed as a near-miss (logs purged, access limited).

## Timeline
- 09:10 — debug log line shipped in transcription-svc v1.42 (incident).
- 11:05 — AppSec spots `transcript=` in a Datadog sample during onboarding review.
- 11:20 — line reverted; hotfix deployed.
- 12:30 — Datadog index purged of affected lines; access list reviewed.

## Root cause
No SAST rule blocks PHI variable names in log calls. Exception handler logged
`request.body` by default. Structured logging not enforced.

## Action items
1. Ship the `phi-in-logs` Semgrep rule and make it blocking in CI. (owner: AppSec)
2. Add Datadog PHI scrubbing rules as defense-in-depth. (owner: Platform)
3. Replace default exception logging with a redacting formatter. (owner: Pipeline)

## Lessons
- PHI-in-logs is the most likely day-to-day HIPAA violation; tooling must catch it.
- Manual review found this — detection coverage is a gap.
