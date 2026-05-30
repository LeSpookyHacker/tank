# 1:1 cadence map

> Who meets with whom, when, and what for. Useful for spotting who's
> in the loop on a given decision.

## Direct reports (Priya's tree)

| Direct | Cadence | Day/Time (Pacific) |
| --- | --- | --- |
| Marcus Chen | weekly | Mon 10:00 |
| Alice Tanaka | weekly | Mon 14:00 |
| Yui Tanaka | weekly | Tue 09:30 |
| Raj Patel | bi-weekly | alternating Wed 11:00 |

## Tom's directs (CTO)

| Direct | Cadence | Day/Time (Pacific) |
| --- | --- | --- |
| Jordan Lee (VP Eng) | weekly | Mon 09:00 |
| **YOU** (first security hire) | weekly | Tue 11:00 (you start week 1) |

## Cross-team standing meetings

| Meeting | Owner | Cadence | Attendees | Purpose |
| --- | --- | --- | --- | --- |
| Platform sync | Yui | weekly Wed 10:00 | Yui, Alice, Marcus, Priya | Platform-org alignment |
| Incident review | Alice | bi-weekly Fri 14:00 | Alice, Carlos, Diana, on-call leads | Walk recent incidents (SRE-run) |
| Eng all-hands | Tom | monthly first Wed | All of eng | Strategy + announcements |
| Pen-test debrief | external | quarterly | TBD with vendor in May 2026 | Reviewing latest pen-test |

## Suggested first-month additions for the new hire

- 30-min intros with each of: Marcus, Alice, Yui, Raj, Lukas, Sam in
  week 1.
- 60-min "deep dive" with Marcus on identity-svc in week 2.
- 60-min "deep dive" with Yui on Platform infrastructure in week 2 or 3.
- Skip-level with Tom in week 3 or 4.

## Open security gaps waiting for an owner (i.e. you)

(No one owns these today — they've been handled reactively by SRE or
not at all. Tom flagged them in your offer conversations.)

1. Snyk-finding triage workflow (who owns? what severity bar opens
   a JIRA? what SLA?). Currently nobody triages.
2. Vault audit-log alerting. Logs exist; nothing watches them.
3. IR escalation path. Today it's "page the SRE on-call." Needs a real
   security escalation structure.
4. JWT key rotation fire-drill. Marcus has the runbook; needs an
   exercise.
