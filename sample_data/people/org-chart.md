# Helix Robotics — engineering org chart

> As of 2026-05. Pulled from BambooHR; spot any drift, ping HR.

```
Sara Goldstein (CEO)
└── Tom Brandt — CTO — tom.brandt@helixrobotics.com
    ├── YOU — Security Engineer (new hire; first dedicated security hire)
    └── Jordan Lee — VP Engineering — jordan.lee@helixrobotics.com
        ├── Priya Shah — Director of Eng, Platform — priya.shah@helixrobotics.com
        │   ├── Marcus Chen — Staff Eng, Identity team
        │   │   └── Sam Liu — Backend, Payments team
        │   ├── Alice Tanaka — SRE Lead
        │   │   ├── Carlos Reyes — Senior SRE
        │   │   └── Diana Okoro — Senior SRE (Platform reliability)
        │   ├── Yui Tanaka — Staff Eng, Platform
        │   └── Raj Patel — FinOps Lead (cross-functional, IAM)
        └── Lukas Bauer — Frontend Lead — lukas.bauer@helixrobotics.com
            ├── Frontend Eng 1
            └── Frontend Eng 2
```

## Notes for the new hire

- **Tom Brandt (CTO)** is your direct manager — you're the first dedicated
  security hire and report straight to him. Weekly 1:1 every Tuesday 11am.
- **Priya Shah** (Director of Eng, Platform) is your closest engineering
  partner; most of the services you'll harden sit in her org.
- **Diana** (Senior SRE) has done the most security-adjacent firefighting —
  she set up the Datadog alerts and ran past incidents reactively because
  no one owned security. She's a partner, not a security owner; the function
  is now yours.
- **Sara** (CEO) doesn't normally meet new ICs, but she runs a monthly
  "Sara's coffee" where any IC can sign up for a 20-min slot. Worth
  doing once in month 2 or 3.
- **Sam, Marcus, Alice, Yui, Raj, Lukas** are the people you'll work
  with most directly day-to-day.
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
- **SRE** (Alice + Carlos + Diana) — owns observability, on-call, incident
  response coordination, and the Datadog SIEM/alerting that has so far been
  run reactively (no dedicated security owner until now).
- **Frontend** (Lukas + 2) — owns `dashboard-web` and customer SDKs.
- **Data** (1 eng + Snowflake vendor) — owns `analytics-pipeline`.
- **Security** (you — the first and only dedicated security hire) — owns
  AppSec, cloud security, the program, and detection/IR strategy. There was
  no security function before you; you inherit a pile of reactive,
  SRE-maintained tooling and unowned playbooks.

## Who NOT to ping for what

- Sara is hands-off on engineering. Go via Tom.
- Tom (your manager) is hands-off on day-to-day technical decisions. For
  platform/service questions go via Priya.
- Marcus is heads-down on a JWT rotation effort and is rate-limiting
  meetings. Async-first.
- Alice will not approve any prod change without a written runbook +
  rollback plan. Plan accordingly.
