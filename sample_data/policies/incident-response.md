# Incident Response Plan

**Owner:** Unowned — interim-held by Tom Brandt (CTO); transfers to the incoming first security hire
**Effective:** 2026-01-15
**Last fire-drill:** 2025-11-02 (tabletop, payments-api scenario)

## What counts as a security incident

Anything matching one of these triggers, no matter how minor it looks:

- Confirmed credential exposure (key in a public repo, password in a
  Slack DM, etc.)
- Suspected or confirmed unauthorized access to a prod system
- Customer data accessed by anyone outside the documented access
  path
- Service compromised by an external attacker (RCE, container
  escape, etc.)
- Data exfiltration suspected (anomalous egress, unexpected S3
  downloads, etc.)
- Supply-chain compromise (malicious package in a build, compromised
  CI runner)

Anything ambiguous, treat as an incident until ruled out. Cost of
declaring is low; cost of missing is high.

## Severity tiers

| Sev | Definition | Page on weekend? |
| --- | --- | --- |
| Sev-1 | Customer data exfiltrated or imminently at risk | Yes |
| Sev-2 | Prod access by unauthorized party, no data exfil confirmed | Yes |
| Sev-3 | Internal-only compromise (employee account, dev system) | No (business hours) |
| Sev-4 | Suspected only, investigating | No (business hours) |

## Roles during an incident

1. **Incident Commander (IC)** — runs the response. Today this defaults
   to the SRE on-call lead (Alice Tanaka), since there is no security
   owner yet; once the first security hire is up to speed, security-class
   incidents move to them.
2. **Tech Lead** — closest engineer to the affected system.
3. **Comms Lead** — Tom for Sev-1; Priya for Sev-2; otherwise IC.
4. **Scribe** — designated by IC at incident start. Logs every
   decision in `#incident-active`.

## Phases

### Detect

Datadog alerts the `#security-alerts` channel. Any human can declare
by typing `!incident <one-line summary>` in `#security-alerts`.

### Triage (≤ 15 min)

IC assigned, severity set, scribe assigned, war-room opened
(`#incident-<incident-id>`).

### Contain

Goal: stop the spread. Common actions:

- Rotate any exposed credential (use `runbooks/rotate-customer-api-key.md`
  and analogues).
- Disable affected user accounts via Okta admin console.
- Network-isolate compromised pods via NetworkPolicy.
- Snapshot disks/volumes before any cleanup that destroys evidence.

### Eradicate

Remove attacker access. Patch the vulnerability. Document the
patched state.

### Recover

Bring services back. Run smoke tests.

### Postmortem

Within 5 business days for Sev-1/Sev-2. Blameless. Filed under
`postmortems/` in this repo.

## Communication

- Internal: `#incident-<id>` for the war room; `#security-alerts`
  for tracking.
- Customer notification: Sev-1 with confirmed customer data exposure
  requires notification per the Customer Master Agreement
  (typically within 72 hours). Tom + legal handle.
- Regulatory: GDPR data breaches require notification to supervisory
  authority within 72 hours. Today, only data-tier confidential
  reaches GDPR scope.

## After-action

- Postmortem filed
- Action items tracked in Jira `HELIX-PM` project
- Action items reviewed at incident-review meeting (bi-weekly Fri 2pm)
- 30-60-90 follow-up to ensure action items closed
