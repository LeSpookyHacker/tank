# Runbook — PHI Breach Response

> Owner: AppSec + HIPAA Privacy Officer · Severity: SEV-1

## When to use
Any confirmed or suspected unauthorized access, disclosure, or loss of PHI
(audio, transcripts, notes, token maps, or CMEK keys).

## Breach clock
The HIPAA/HITECH 60-day notification clock starts at **discovery** time. Record
the discovery timestamp first, before anything else.

## Steps

1. **Declare & record.** Open an incident; log discovery time, who discovered it,
   and the suspected data scope (which tenants/patients).
2. **Contain.** Revoke the implicated credential/SA; if a tenant CMEK is at risk,
   rotate or disable the key; isolate the affected Cloud Run revision.
3. **Preserve.** Snapshot relevant `audit_events`, Cloud Logging, and Datadog
   before they roll off. Audit logs are append-only — export, don't mutate.
4. **Scope.** Use `audit_events` (actor, action, resource, tenant) to determine
   exactly which records were accessed and by whom.
5. **Eradicate.** Patch the root cause (e.g. over-broad SA, scrubbing gap).
6. **Notify.** Privacy Officer assesses reportability; notify affected covered
   entities per BAA and HITECH timelines.
7. **Recover & review.** Restore normal operations; schedule a postmortem;
   capture lessons.

## Key contacts
HIPAA Privacy Officer (Tom Bryce), CTO (Aanya Krishnan), Platform on-call (Dana).
