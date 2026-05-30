# Postmortem — leaked AWS access key (close call) 2026-04-11

**Severity:** Sev-2 (containment within 1 hour, no confirmed access)
**Duration:** 09:14 – 10:08 UTC (54m)
**Incident commander:** Alice Tanaka (SRE Lead)
**Tech lead:** Raj Patel
**Comms:** Priya Shah
**Author:** Alice Tanaka (SRE Lead)

## Summary

A long-lived IAM access key for `iam-user/ci-snyk` was accidentally
committed to a **public** GitHub repo (a fork the engineer was
using for an open-source contribution). GitHub Secret Scanning
alerted AWS within 4 minutes; AWS automatically applied the quarantine
policy. We rotated the key and confirmed no API calls had used it
post-leak.

This was close. If GitHub's scanner had been slower, or if we'd
been the kind of shop that ignores those alerts, this could have
been very bad.

## Customer impact

None confirmed. CloudTrail shows zero API calls from the leaked key
between leak time (09:08) and rotation completion (09:51).

## Timeline (UTC)

| Time | Event |
| --- | --- |
| 09:08 | Engineer (name withheld) pushes a commit to their public fork. The commit accidentally includes a `.env` file with `AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE` and the matching secret. |
| 09:12 | GitHub Secret Scanning detects the AWS key. |
| 09:14 | AWS receives the GitHub report. AWS Quarantine SCP applied to `iam-user/ci-snyk`. |
| 09:14 | AWS sends notification email to security@helixrobotics.com and root account contact. |
| 09:19 | Alice (SRE on-call) sees the email, declares Sev-2 in `#security-alerts`. |
| 09:23 | Raj joins; confirms the user was `iam-user/ci-snyk` (used by Snyk SaaS for CodeArtifact reads). |
| 09:30 | Raj generates a new access key and updates the Snyk SaaS config. |
| 09:42 | Snyk integration confirmed working with the new key. |
| 09:48 | Alice queries CloudTrail for any API calls using the leaked AccessKeyId in the last 24h. **Zero hits.** |
| 09:51 | Old key deleted. |
| 09:58 | Engineer notified, paired with Raj on a cleanup of git history on the public repo. |
| 10:08 | Incident closed. |

## Root cause

Two contributing factors:

1. **A long-lived IAM access key existed in the first place.** The
   `iam-user/ci-snyk` user predates our move to OIDC-based GitHub
   Actions and was never migrated. It's been on our kill list
   (HELIX-1879) for 7 months.
2. **An engineer copied production credentials into a `.env` file
   on their laptop** to test something locally. The `.env` was in
   `.gitignore` on the company repo but the engineer was working in
   a personal fork without the same `.gitignore`.

## Why this was a close call, not a disaster

- GitHub Secret Scanning caught it in <4 minutes.
- AWS Quarantine SCP applied automatically.
- We had `security@helixrobotics.com` configured as an AWS
  notification target.
- Alice (SRE on-call) was at her desk and triaged within 5 minutes of the email.

## Action items

- [x] Rotate `iam-user/ci-snyk` (raj.patel, completed 2026-04-11)
- [ ] Migrate `iam-user/ci-snyk` to OIDC trust + delete IAM user
      (raj.patel, due 2026-05-31) — **HELIX-1879**
- [ ] Migrate `iam-user/legacy-jenkins` similarly
      (raj.patel, due 2026-06-15)
- [ ] Implement a CI check that fails on any commit containing
      detect-secrets findings (security@, due TBD — this is the
      new hire's first big project candidate)
- [ ] All-hands reminder: never copy prod credentials onto laptops;
      use Vault dev mode (tom.brandt, completed 2026-04-12)
- [ ] Set up a per-user IAM key inventory dashboard
      (raj.patel, ongoing)

## Lessons learned

1. **Long-lived keys are a ticking clock.** This one just happened
   not to detonate.
2. **External secret scanning is a real defense.** Worth ensuring
   our `security@` mailbox stays staffed.
3. **Personal forks of work repos are a common leak vector.** The
   engineer in question wasn't trying to be careless — they were
   contributing to an OSS project. Better tooling on the laptop side
   (pre-commit hook for detect-secrets) would have caught this.

## What this surfaces for the new security hire

The next security engineer to join Helix (you) should consider this
incident the canonical example of **why your first 90 days should
prioritize**:

- A working vulnerability-management workflow.
- Killing the remaining long-lived IAM users.
- A CI/laptop-side secret-detection layer.

Priya has already flagged all three as priorities; this incident
moves them from "should do" to "must do, soon."
