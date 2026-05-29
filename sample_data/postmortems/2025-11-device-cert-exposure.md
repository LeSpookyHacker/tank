# Postmortem: Device Certificate Private Key Exposure via Oversized S3 Pre-Signed URL TTL

**Incident ID**: INC-2025-0047  
**Date**: 2025-11-14  
**Severity**: P1 (near-miss — no confirmed exfiltration)  
**Duration**: 6 hours 22 minutes (07:14 – 13:36 PST)  
**Services affected**: `webhook-router`, `device-registry`  
**IC**: diana.okoro@helixrobotics.com  
**Participants**: yui.tanaka@helixrobotics.com, alice.tanaka@helixrobotics.com,
tom.brandt@helixrobotics.com (notified), marcus.chen@helixrobotics.com (SME)

---

## Summary

`webhook-router` generates S3 pre-signed URLs for device certificate provisioning
— these URLs allow OEM customer devices to download their mTLS client certificates
during initial setup. A misconfiguration in a recent `webhook-router` deploy set
the TTL of these pre-signed URLs to **7 days** instead of the intended **5 minutes**.

The oversized TTL was live for 6 hours before Datadog alerted on an anomalous
S3 download pattern. During that window, approximately 240 pre-signed URLs were
generated and sent to OEM customers via webhook. No URLs were confirmed to have
been accessed by unauthorized parties, but we cannot rule it out.

The device cert private keys referenced by these URLs are stored in Vault and
are not directly embedded in the certificates — the URLs gave access to the
**public certificate** and the **certificate chain** only. Device private keys
remain in Vault. However, access to the public certificate allows an attacker to
mount a man-in-the-middle attack against device→Helix mTLS sessions for the
duration of the cert TTL (90 days).

---

## Timeline

| Time (PST) | Event |
| --- | --- |
| 07:14 | `webhook-router` v1.8.2 deployed to production (included pre-signed URL TTL change — code review missed it) |
| 07:15 | First pre-signed URL with 7-day TTL generated and delivered to OEM customer device |
| 09:30 | Automated daily deploy of new certs triggers 80+ pre-signed URL generations within 3 minutes |
| 11:02 | Datadog alert fires: "Unusual S3 presigned URL volume from webhook-router" |
| 11:15 | Diana pages platform-on-call; Yui begins investigation |
| 11:34 | Root cause identified (TTL misconfiguration in v1.8.2) |
| 11:50 | `webhook-router` v1.8.3 deployed with TTL reverted to 5 minutes |
| 12:10 | S3 Object Lock applied to device-cert bucket: new pre-signed URLs cannot exceed 10 minutes |
| 13:00 | OEM customers with affected URLs notified (form letter, see HELIX-INC-2025-0047-notification) |
| 13:36 | Incident closed (P1 → post-incident review phase) |

---

## Root cause

A pull request in `webhook-router` added configurable pre-signed URL TTL as a
feature (for future use with different cert types). The default was set to 7 days
as a "safe maximum" by the author (yui.tanaka), without consulting the security
team. The code reviewer (kwame.asante@helixrobotics.com) approved the PR without
flagging the TTL change.

There was no security review gate on configuration changes affecting credential
or certificate exposure windows.

---

## Contributing factors

1. **No security review requirement for TTL-related config changes** — TTL
   changes in `webhook-router` do not trigger the security review checklist.
2. **No automated TTL cap at the infrastructure layer** — S3 bucket policy
   did not enforce a maximum TTL on pre-signed URLs. This is now fixed.
3. **Detection gap** — the Datadog alert for bulk pre-signed URL generation
   existed but fired at a threshold (80 URLs/3min) that was only reached at
   09:30, not at 07:14 when the first URLs were generated.
4. **No rotation after TTL extension incident** — once the TTL was reverted,
   we did not immediately rotate or revoke the 240 affected URLs. (Not possible
   without Object Lock or S3 Lifecycle action — now tracked as HELIX-2120.)

---

## Impact

- **Confidentiality**: Low. Public certificates only, not private keys.
- **Integrity**: No unauthorized writes observed.
- **Availability**: No availability impact.
- **Regulatory**: Notified OEM customers per contract clause 12.4 as precaution.
  No GDPR notification required (device certs are not personal data under our
  DPA interpretation).

---

## Action items

| # | Action | Owner | Due | Status |
| --- | --- | --- | --- | --- |
| 1 | Add S3 bucket policy to cap pre-signed URL TTL at 10 minutes for device-cert bucket | yui.tanaka | 2025-11-21 | ✅ Done (done at 12:10 during incident) |
| 2 | Add security-checklist item: "Does this change affect credential/cert TTLs?" | diana.okoro | 2025-11-28 | ✅ Done |
| 3 | Reduce Datadog alert threshold for bulk pre-signed URL volume to 10 URLs/5min | diana.okoro | 2025-12-01 | ✅ Done |
| 4 | Write Sigma rule for S3 bulk pre-signed URL generation | diana.okoro | 2025-12-15 | 🔄 In progress |
| 5 | Evaluate whether pre-signed URL audit logs should go to SIEM in real-time | diana.okoro | 2026-01-15 | ⬜ Open |
| 6 | Investigate feasibility of S3 pre-signed URL revocation (HELIX-2120) | yui.tanaka | 2026-02-01 | ⬜ Open |

---

## Lessons learned

1. **S3 pre-signed URL TTL must be capped at the bucket policy layer** —
   application-layer TTL enforcement is bypassable. Any bucket that serves
   sensitive data should have an `s3:PutObjectAcl` or `s3:GetObject` condition
   capping the `s3:signatureAge`.

2. **Configuration changes affecting security-relevant TTLs require a security
   review** — the PR checklist must include: "Does this change affect how long
   a credential, certificate, or signed URL remains valid?"

3. **Detection should fire on the first anomalous event, not on volume** —
   a single 7-day pre-signed URL for device certs should have been alertable.
   Low-and-slow attacks will bypass volume-based thresholds.

4. **Incident response timelines under GDPR begin from when PII was potentially
   accessible, not from confirmed exfiltration** — though device certs are not
   PII, this principle applies to any incident where sensitive data was exposed
   for an extended window even without confirmed access.

---

## Thanks

Diana Okoro and Yui Tanaka for fast incident response. Alice Tanaka for running
comms with OEM customers. Marcus Chen for the JWKS and mTLS cert architecture
context.
