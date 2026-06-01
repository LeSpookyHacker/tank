# Vulnerability Management SLA Policy

> Owner: AppSec · Status: Draft v1.0

## Severity → remediation SLA

| Severity | Definition | Remediation SLA |
|---|---|---|
| Critical | PHI breach, auth bypass, RCE, key compromise | 7 days |
| High | Significant exploitable risk | 30 days |
| Medium | Conditional / limited risk | 90 days |
| Low | Minimal risk | Next normal cycle / 180 days |

## Severity adjustment (HIPAA context)

Base CVSS is adjusted up one band when the asset processes PHI (data_tier=phi
in the CMDB) or when exploitation would break the clinician approval gate or the
PHI de-identification boundary. See `vuln-mgmt/risk-scoring` for the formula.

## Intake sources

NVD CVE feed, GitHub Dependabot, Semgrep/Trivy CI findings, pentest, and
responsible-disclosure reports. All land in the vulnerability intake queue,
get triaged (severity + owner + due date), then closed (patched / accepted /
won't-fix) or promoted to the risk register.

## SLA breach handling

A vuln past SLA escalates to the service owner's manager and is surfaced in the
weekly security digest and the security-program dashboard.
