# 1:1 cadence map

> Who meets with whom, when, and what for. Useful for spotting who's
> in the loop on a given decision.

## Direct reports (Priya's tree)

| Direct | Cadence | Day/Time (Pacific) |
| --- | --- | --- |
| Marcus Chen | weekly | Mon 10:00 |
| Alice Tanaka | weekly | Mon 14:00 |
| Yui Hayashi | weekly | Tue 09:30 |
| Raj Patel | bi-weekly | alternating Wed 11:00 |
| Diana Okoro | weekly | Thu 10:30 |
| **YOU** | weekly | Tue 11:00 (you start week 1) |

## Cross-team standing meetings

| Meeting | Owner | Cadence | Attendees | Purpose |
| --- | --- | --- | --- | --- |
| Platform sync | Yui | weekly Wed 10:00 | Yui, Alice, Marcus, Priya | Platform-org alignment |
| Incident review | Diana | bi-weekly Fri 14:00 | Diana, Alice, on-call leads | Walk recent incidents |
| Security sync | Diana → you+Diana | weekly Mon 09:30 | Diana, you (incoming), Priya (drop-in) | Security team coordination |
| Eng all-hands | Tom | monthly first Wed | All of eng | Strategy + announcements |
| Pen-test debrief | external | quarterly | TBD with vendor in May 2026 | Reviewing latest pen-test |

## Suggested first-month additions for the new hire

- 30-min intros with each of: Marcus, Alice, Yui, Raj, Lukas, Sam in
  week 1.
- 60-min "deep dive" with Marcus on identity-svc in week 2.
- 60-min "deep dive" with Yui on Platform infrastructure in week 2 or 3.
- Skip-level with Tom in week 3 or 4.

## Decisions Diana has flagged as "needs you" once you start

(From her welcome doc, abbreviated.)

1. Snyk-finding triage workflow (who owns? what severity bar opens
   a JIRA? what SLA?). Diana wants this off her plate.
2. Vault audit-log alerting. Logs exist; nothing watches them.
3. IR escalation path. Today it's "page Diana." Needs structure.
4. JWT key rotation fire-drill. Marcus has the runbook; needs an
   exercise.
