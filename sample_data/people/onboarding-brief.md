# Welcome to Helix Security — Notes for the Incoming Security Engineer

**From**: Tom Brandt (CTO)  
**To**: Incoming Security Engineer  
**Date**: 2026-04-25  
**Classification**: Internal

---

## Why this role, why now

Helix has been fortunate. We have great engineers who care about security, and
Diana Okoro has kept our detection and incident response function running almost
single-handedly. But we are past the point where we can treat security as a
shared responsibility that nobody owns strategically.

Three things are converging:

1. **SOC 2 Type II audit window opens September 2026.** Our Type I was clean, but
   Type II is an operating-effectiveness audit — auditors watch us run for 12
   months. We need the program to be solid before the window opens, not scrambling
   after.

2. **Customer compliance pressure is increasing.** Three enterprise deals in Q1
   stalled or required additional security questionnaire rounds. One prospect
   (Series C logistics company) asked for a pentest report. We don't have one.

3. **Our PII and payment footprint is growing.** We're processing more charges and
   storing more billing addresses than we were 18 months ago. The risk surface
   isn't shrinking.

You are the person I've been looking for to own this.

---

## What I need from you in 90 days

I've shared the full 90-day plan expectations during our offer conversations, but
the short version:

### First 30 days — understand and document
- Walk every service with its owner. Start with identity-svc (Marcus), payments-api
  (Sam), and pii-vault (currently unowned — this is a problem).
- Get a copy of our open security debt. Diana has the Datadog searches; Raj has the
  IAM picture; Priya has the architecture notes she's been keeping.
- Sit in on platform-on-call handoff once. Security incidents often start there.

### Days 30–60 — fix the most pressing things
Three things I want done or substantially in-progress by day 60:

1. **Vulnerability management workflow** (HELIX-2106). We have Dependabot,
   Inspector, and Security Hub, but nobody owns triage or remediation SLAs. Critical
   CVEs are sitting open for >30 days. Pick a tool, define a workflow, get buy-in
   from Priya.

2. **Kill the long-lived IAM users** (HELIX-1879). `iam-user/ci-snyk` and
   `iam-user/legacy-jenkins` should have been OIDC-migrated a year ago. The
   ci-snyk key almost bit us in April (see the April 11 postmortem). Raj owns
   the migration work; you own getting it done.

3. **CI-side secret detection** (action item from the April postmortem). Every
   repo needs `detect-secrets` in CI. Diana scoped the work; it's a first-project
   candidate for you.

### Days 60–90 — program foundation
- Own the secrets management policy (SEC-POL-003, currently held by Diana as
  interim owner).
- Write or adopt an incident response runbook for pii-vault (RB-SEC-004 is the
  placeholder, also held by Diana right now).
- Give me a written summary of our biggest unaddressed risks and a prioritized list
  of what you plan to tackle next. This feeds directly into the SOC 2 prep.

---

## People to meet in week 1

| Person | Why |
| --- | --- |
| **Diana Okoro** | She owns detection, SIEM, security on-call, and Vault admin today. She knows more about our incident history than anyone. Sit with her first. |
| **Alice Tanaka** | SRE lead, runs platform-on-call, holds the break-glass credentials. She's seen most of our operational incidents. |
| **Raj Patel** | FinOps lead and de-facto IAM governor. He knows every long-lived credential and AWS permission set. |
| **Marcus Chen** | Staff engineer, owns identity-svc. The most security-conscious engineer on the team. He's been keeping a list of identity gaps for months. |
| **Sam Liu** | Owns payments-api. PCI scope. Good instincts, will be a strong partner on the AppSec side. |
| **Priya Shah** | Your manager. She has architecture notes on security gaps across services — ask for her "threat surface" writeups. |

---

## Open tickets to be aware of

The Jira backlog has more security debt than any one person can fix at once. These
are the ones I think of as the most important:

| Ticket | Summary |
| --- | --- |
| HELIX-1879 | Migrate long-lived IAM users to OIDC — started, needs an owner to finish |
| HELIX-2031 | analytics-pipeline static Snowflake creds — exemption expires 2026-09-01 |
| HELIX-2090 | pii-vault service owner is vacant — assign yourself if it makes sense |
| HELIX-2095 | Break-glass access to pii-vault has no automated alert — 30-day manual audit gap |
| HELIX-2098/2099/2100 | analytics cross-account IAM role is over-broad — Raj started a review |
| HELIX-2106 | No vuln remediation SLA — critical CVEs aging past 30 days |
| HELIX-2111 | CMK deletion protection not enforced via SCP — quick win |

---

## A note on Diana

Diana has been the entire security function at Helix for a year and a half. She
has been doing the job of two people. She will be an invaluable partner and she
deserves credit for the posture we have today. Please coordinate with her, not
around her.

Her domain is detection, response, and Vault operations. Yours is security
engineering, AppSec, cloud security, and the program. There will be natural
overlap — work it out together.

---

## One final thing

We are not a security-first company yet. We are a company that is becoming one.
That means you will spend time educating, negotiating, and convincing people who
have always shipped first and patched later. I am asking you to do that work, and
I will back you up when you need it.

If you hit a wall — a team that won't prioritize a fix, an exception request you
think is too risky, a process change that needs top-down support — come to me.
That is what I'm here for.

Welcome aboard.

— Tom
