# Runbook — Cross-Tenant Access Investigation

> Owner: AppSec · Relates to T-011 (privilege escalation), T-008 (token-map leak)

## When to use
An alert or report suggests one tenant's data was accessible to another tenant —
e.g. an admin endpoint returned another tenant's clinicians, or a SOAP note
contained PHI from the wrong patient.

## Steps

1. **Freeze evidence.** Export `audit_events` for both tenants around the window
   (`tenant_id`, `actor_id`, `resource_id`, `outcome`).
2. **Confirm the boundary crossed.** Determine if it was: (a) authz failure on an
   admin endpoint (`tenant_id` trusted from request → T-011), or (b) wrong token
   map on re-injection (T-008).
3. **Scope impact.** Enumerate exactly which records of Tenant B were exposed to
   Tenant A. Hash patient IDs in the writeup.
4. **Contain.** Disable the implicated endpoint/feature; revoke the actor's
   session; if T-008, halt the affected pipeline session class.
5. **Assess reportability.** Cross-tenant PHI exposure is almost always a
   reportable breach — engage the Privacy Officer immediately (see PHI breach
   runbook).
6. **Fix root cause.** Enforce server-side `tenant_id` from the verified IdP
   claim; validate HMAC session binding before token re-injection.
7. **Postmortem + lessons.**
