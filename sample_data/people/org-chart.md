# Helix Robotics — engineering org chart

> As of 2026-05. Pulled from BambooHR; spot any drift, ping HR.

```
Sara Okafor (CEO)
└── Tom Brennan — VP Engineering — tom.brennan@helixrobotics.com
    ├── Priya Shah — Director of Eng, Platform — priya.shah@helixrobotics.com
    │   ├── Marcus Chen — Staff Eng, Identity team
    │   │   └── Sam Liu — Backend, Payments team
    │   ├── Alice Tanaka — SRE Lead
    │   ├── Yui Hayashi — Staff Eng, Platform
    │   ├── Raj Patel — FinOps Lead (cross-functional, IAM)
    │   └── Diana Okoro — Detection & Response
    │       └── YOU — Security Engineer (new hire)
    └── Lukas Bauer — Frontend Lead — lukas.bauer@helixrobotics.com
        ├── Frontend Eng 1
        └── Frontend Eng 2
```

## Notes for the new hire

- **Priya** is your direct manager. Weekly 1:1 every Tuesday 11am.
- **Diana** is your peer on the security side. Daily standup at 9:30am
  (informal, in Slack `#security-team`). She covers Detection & Response;
  you cover AppSec / Cloud Sec / general.
- **Tom** (skip) does monthly skip-levels, typically 30 minutes the
  first Friday of the month.
- **Sara** (CEO) doesn't normally meet new ICs, but she runs a monthly
  "Sara's coffee" where any IC can sign up for a 20-min slot. Worth
  doing once in month 2 or 3.
- **Sam, Marcus, Alice, Yui, Raj, Lukas** are the people you'll work
  with most directly day-to-day.

## Team boundaries

- **Identity team** (Marcus + 2 contractors) — owns `identity-svc`
  and the internal CA.
- **Payments team** (Sam + 1 backend eng) — owns `payments-api` and
  `pii-vault` (though pii-vault is moving to Security ownership in
  Q3).
- **Platform team** (Yui + 2 platform engs) — owns `orders-api`,
  `webhook-router`, `device-registry`, EKS, IAM, Terraform.
- **SRE** (Alice + 1) — owns observability, on-call, incident response
  coordination.
- **Frontend** (Lukas + 2) — owns `dashboard-web` and customer SDKs.
- **Data** (1 eng + Snowflake vendor) — owns `analytics-pipeline`.
- **Detection & Response** (Diana + you eventually share this) — owns
  Datadog SIEM, alerting, IR playbooks.
- **Security** (you, until headcount grows) — owns everything else.

## Who NOT to ping for what

- Sara is hands-off on engineering. Go via Tom.
- Tom is hands-off on day-to-day technical decisions. Go via Priya.
- Marcus is heads-down on a JWT rotation effort and is rate-limiting
  meetings. Async-first.
- Alice will not approve any prod change without a written runbook +
  rollback plan. Plan accordingly.
