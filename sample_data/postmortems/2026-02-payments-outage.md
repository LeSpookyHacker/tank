# Postmortem — payments-api outage 2026-02-17

**Severity:** Sev-1 (customer-impacting outage)
**Duration:** 14:02 – 18:09 UTC (4h 7m)
**Incident commander:** Alice Tanaka
**Tech lead:** Sam Liu
**Comms:** Tom Brandt
**Authors:** Sam Liu, Alice Tanaka

## Summary

For four hours on the afternoon of 2026-02-17, payments-api returned
500s for ~80% of charge attempts. Root cause was a stale Vault token
in the Vault Agent sidecar after an upstream Vault leader election.
The sidecar didn't re-authenticate; the application kept using its
cached token, which had expired. Stripe API calls succeeded, but the
DB session pool got into a stuck state because we couldn't read fresh
DB credentials.

## Customer impact

- ~38k failed charges across 219 customers.
- Stripe-side retries succeeded for ~70% of failed charges after the
  outage ended; manual retries cleaned up the rest.
- Two customers escalated via support; both received SLA credits.
- No data loss. No data exposure.

## Timeline (UTC)

| Time | Event |
| --- | --- |
| 13:48 | Vault leader election in `vault.helix.internal` cluster (one node OOM-killed). Healthy quorum restored within 8s. |
| 14:02 | First user-impacting 5xx spike on payments-api. |
| 14:05 | Datadog `payments-api-5xx` alert pages Sam. |
| 14:08 | Sam confirms widespread 500s. Pages Alice for incident command. |
| 14:11 | Sev-1 declared. `#incident-2026-02-17-payments` opened. |
| 14:18 | Status page updated; Tom notified. |
| 14:25 | First hypothesis: Stripe outage. Stripe status page clean; this is wrong. |
| 14:42 | Second hypothesis: DB issue. RDS metrics flat; DB itself healthy. |
| 15:10 | Sam notices Vault Agent logs show repeated "token expired" warnings. |
| 15:23 | Diana joins to assist with auth-side investigation. |
| 15:55 | Sam attempts `kubectl rollout restart deploy/payments-api`; partial recovery on the restarted replicas. |
| 16:30 | Root cause confirmed: Vault Agent sidecar version 1.13.x has a known bug where token renewal can silently stop after a Vault leader change. |
| 17:15 | Decision: roll all payments-api pods to force fresh Vault auth. |
| 17:42 | All replicas rolled. Error rate dropping. |
| 18:09 | Error rate back to baseline. Incident closed. |

## Root cause

Vault Agent (sidecar in payments-api pods) was running version
1.13.4, which has a known issue where token renewal can wedge after
an upstream Vault leader change. Our token TTL was 24 hours, so the
problem only manifested after the existing tokens expired (~14:02,
roughly 14 hours after the leader election at 23:48 the previous
day — coincidence that nobody noticed sooner).

The fix in Vault Agent 1.14+ is straightforward; we just hadn't
upgraded.

## Why our defenses didn't catch it

1. **No Vault token-age alert.** We monitor Vault server health
   but not the age/freshness of tokens being used by clients. If
   we had a "tokens older than 90% of their TTL" alert, we'd have
   caught this hours earlier.
2. **The Vault Agent logs were buried.** Datadog ingests stdout
   from every pod, but the Vault Agent's "token expired" messages
   weren't matched by any alert query.
3. **Wrong first hypothesis.** Stripe outages have caused two prior
   payments incidents this year, so it was the natural first guess.
   We didn't pivot fast enough.

## Action items

- [x] Upgrade Vault Agent to 1.14.4 across all services
      (sam.liu, completed 2026-02-22)
- [x] Add Datadog alert on token-age > 75% TTL
      (alice.tanaka, completed 2026-02-23)
- [ ] Document a Vault-side incident playbook
      (alice.tanaka, due 2026-03-15) — **OVERDUE**
- [ ] Audit Vault Agent versions across all services quarterly
      (yui, recurring) — first occurrence pending
- [ ] Improve auth-related troubleshooting in the payments-api
      runbook (sam.liu, due 2026-03-10) — **OVERDUE**

## Lessons learned

1. **Cached auth state needs freshness alerts**, not just availability
   alerts. We were watching the wrong thing.
2. **First-hypothesis bias** cost us 30+ minutes. Force a "rule out
   our own stack" check in the runbook.
3. **Upgrade discipline** matters even for sidecars. The bug was
   fixed 6 months before it bit us.

## What did NOT cause the outage (for posterity)

- Stripe (their side was healthy throughout)
- RDS (DB health checks were green; only the credential rotation
  layer was broken)
- A bad deploy (no deploys in the prior 24h window)
- DNS, networking, EKS itself
