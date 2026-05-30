# Helix Robotics — Tank Sample Data

A synthetic corpus that simulates **what a new Sr/Staff/Manager Security
Engineer might be handed in their first week** at a mid-size B2B SaaS
company called Helix Robotics. None of this is real. All hostnames,
emails, account IDs, secrets, and people are fabricated.

Use this corpus to:

- Smoke-test Tank's ingestion pipeline (every parser type is exercised).
- Watch the redaction layer turn cleartext into placeholders.
- Build a knowledge graph you can chat with.
- Generate all 10 onboarding reports against realistic-looking inputs.
- Trigger the partner-mode nudges (coverage gaps, contradictions,
  pattern detection, expiring decisions).
- Exercise living artifacts: threat models, decisions, design reviews,
  postmortems, tabletops, glossary, lessons, journal.
- Test the DFD tool's 4-mode input and split-panel threat workspace.

## Quickstart

**Step 1 — ingest file artifacts:**

```bash
python -m scripts._gen_fixtures     # synthesize PDF/DOCX/PNG from MD sources (once)
python -m scripts.load_fixtures     # ingest all files into Tank's KB
```

Preview without touching the API:

```bash
python -m scripts.load_fixtures --dry-run
```

**Step 2 — seed DB records (living artifacts, org/team/project, DFDs):**

```bash
python -m scripts.seed_db           # idempotent; safe to re-run
python -m scripts.seed_db --dry-run # print what would be inserted
```

`seed_db.py` creates: org name, 3 teams, 4 projects, 2 pre-analyzed
DFD threat models (payments-api and identity-svc, each with 8–10 STRIDE
threats), 4 decisions, 10 glossary terms, 5 lessons, 1 tabletop
scenario, 3 journal entries, and 3 follow-ups. No API calls are made.

**Step 3 — test the DFD tool manually:**

Upload any `.mmd` file from `sample_data/dfd/` via the DFD tool's
Stage 1 Tab B ("Upload File"). The seed_db.py results are pre-cached,
so Stage 2/3 will load instantly with no API call.

## Scenario

You've just joined **Helix Robotics** as its **first dedicated Security
Engineer**. There was no security team before you — security has been a
side-duty the SRE team (Diana Okoro especially) absorbed reactively.
Helix is ~80 people, Series B (Q3 2025), processing payments and identity
for robotics OEMs. Your scope as the first hire is loosely defined —
somewhere between AppSec, Cloud Sec, and "general security plumbing" —
and you'll spend the next 30/60/90 days figuring out what matters.

Helix's HQ is Austin; satellites in Seattle and Lisbon. The internal
TLD is `helix.internal`. AWS prod account is `999988887777`, staging
`888877776666`, region `us-west-2`.

The on-call persona who joins in this sample dataset is **Mei Watanabe**
(Sr. Security Engineer, start date 2026-04-28). The journal entries and
follow-ups are written from her perspective.

## What's here

```
sample_data/
├── company.md                                # 1-page company overview
├── architecture/                             # high-level system docs
│   ├── 01-platform-overview.md               # → PDF via _gen_fixtures
│   ├── 02-auth-flow.md                       # → PNG via _gen_fixtures
│   ├── 03-data-flow.md                       # mermaid + prose
│   ├── 04-region-map.md                      # AWS accounts, regions
│   ├── 05-identity-svc-detail.md             # OIDC/JWT/RDS design, HELIX-2108
│   └── 06-pii-vault-detail.md               # mTLS, CMK, break-glass, HELIX-2095
├── repos/
│   ├── payments-api/                         # Python FastAPI repo
│   └── webhook-router/                       # Go service
├── cmdb/
│   ├── services.csv                          # 8 services + owners
│   └── cloud-accounts.csv                    # AWS accounts
├── people/
│   ├── org-chart.md                          # engineering org tree
│   ├── on-call.csv                           # rotations
│   ├── 1-1-cadence.md                        # who 1:1s with whom
│   └── team-directory.csv                    # 18-person full roster (5 teams)
├── policies/
│   ├── access-policy.md                      # → DOCX via _gen_fixtures
│   ├── incident-response.md
│   ├── data-classification.md
│   └── secrets-management.md                # SEC-POL-003: Vault adoption + SLAs
├── runbooks/
│   ├── service-restart.md
│   ├── rotate-customer-api-key.md
│   ├── investigate-suspicious-login.md
│   └── respond-to-pii-breach.md             # GDPR 72h, OEM 24h, 6-step containment
├── postmortems/
│   ├── 2026-02-payments-outage.md
│   ├── 2026-04-credential-leak-close-call.md
│   └── 2025-11-device-cert-exposure.md      # INC-2025-0047: S3 pre-signed URL TTL
├── seeds/                                    # planted to test redaction
│   ├── leaked-key-example.md                 # fake AKIA + Slack token
│   └── internal-host-list.md                 # internal hosts + IPs
├── detections/                               # Sigma rules (auto-detected)
│   ├── helix-suspicious-login.yml
│   ├── helix-ec2-metadata-ssrf.yml           # T1552.005, HELIX-1822 SSRF
│   ├── helix-s3-bulk-download.yml            # T1530, >500 GetObject in 5min
│   └── helix-vault-token-anomaly.yml         # T1552.001, off-CIDR Vault auth
├── iam/                                      # IAM policies (auto-detected)
│   ├── prod-s3-policy.json
│   ├── analytics-cross-account-role.json     # over-broad cross-account (findings)
│   └── k8s-rbac-pii-vault.yaml              # K8s RBAC + NetworkPolicy, mild over-perm
├── compliance/                               # Control frameworks (auto-detected)
│   ├── controls-soc2.json
│   └── controls-nist-csf.json               # NIST CSF 2.0, 8 controls, GV/ID/PR/DE
└── dfd/                                      # DFD Mermaid source files (NOT ingested)
    ├── README.md                             # explains: upload via DFD tool Stage 1
    ├── payments-api-dfd.mmd                  # 10 STRIDE threats (pre-seeded)
    ├── identity-svc-dfd.mmd                  # 8 STRIDE threats (pre-seeded)
    ├── pii-vault-dfd.mmd                     # 6 threats, minimal blast radius
    └── webhook-router-dfd.mmd                # SSRF surface, INC-2025-0047 context
```

## Parser coverage

Every parser type Tank ships is exercised by this sample data:

| Parser | Sample file(s) | How dispatched |
| --- | --- | --- |
| MarkdownParser | `architecture/*.md`, `policies/*.md`, etc. | extension `.md` |
| PDFParser | `architecture/01-platform-overview.pdf` | extension `.pdf` |
| DocxParser | `policies/access-policy.docx` | extension `.docx` |
| ImageParser (vision) | `architecture/02-auth-flow.png` | extension `.png` |
| CSVJSONParser | `cmdb/*.csv`, `people/on-call.csv`, `people/team-directory.csv` | extension `.csv` |
| Code summary | `repos/payments-api/`, `repos/webhook-router/` | directory walk |
| SigmaParser | `detections/*.yml` (4 rules) | content-sniff: `logsource`+`detection` |
| IAMParser (JSON) | `iam/prod-s3-policy.json`, `iam/analytics-cross-account-role.json` | content-sniff: `Version`+`Statement` |
| IAMParser (YAML) | `iam/k8s-rbac-pii-vault.yaml` | content-sniff: `kind: ClusterRole` |
| ControlFrameworkParser | `compliance/controls-soc2.json`, `compliance/controls-nist-csf.json` | content-sniff: `framework`+`controls` |

The PDF, DOCX, and PNG files are generated from their markdown sources by
`scripts/_gen_fixtures.py`. Run it once before ingesting:

```bash
python -m scripts._gen_fixtures
```

## Living artifacts seeded by `seed_db.py`

`scripts/seed_db.py` populates Tank's DB with records that would normally
be created through the UI, exercising every living-artifact feature:

| Feature | What's seeded |
| --- | --- |
| **Org / Teams / Projects** | Org renamed "Helix Robotics"; 3 teams (Platform Security, AppSec, Threat Intelligence); 4 projects (Auth Hardening, PII Data Program, Threat Model Coverage, SOC 2 Evidence Sprint — 1 archived) |
| **DFD analyses** | 2 pre-analyzed DFDs with full STRIDE threat JSON: payments-api (10 threats) and identity-svc (8 threats). Both are cached — reopening them in the UI skips the API call. |
| **Decisions** | 4 decisions: 1 `security_invariant` (RS256 JWT keys), 1 `design_choice` (mTLS), 1 `accepted_risk` (SSRF, expires 2026-08-01), 1 `deferred_fix` (RDS IAM auth, expires 2026-07-01). The two expiring decisions will trigger the `decision_expiring` nudge. |
| **Glossary** | 10 unconfirmed terms: PAN, CMK, mTLS, SSRF, dbt, Snowpipe, OEM, device cert, VRT, break-glass. Unconfirmed to let you test the confirmation UX. |
| **Lessons** | 5 lessons from postmortems and design reviews, tagged for search: `dbt`, `pii`, `vault`, `s3`, `incident-response`, `gdpr`, `compliance`, `cmdb`, `oncall`. |
| **Tabletop** | 1 scenario: "Ransomware via compromised analytics pipeline" — 4 timed injects from AssumeRole anomaly through ransom email. Participants: Mei, Diana, Alice, Fatima, Tom. |
| **Journal entries** | 3 entries from Mei Watanabe's first weeks (2026-04-28, 2026-05-07, 2026-05-19), seeded with historical dates. |
| **Follow-ups** | 3 follow-ups: HELIX-2108 RDS IAM auth (7 days), HELIX-1822 SSRF fix (14 days), Stripe SOC 2 report (30 days). |

## Deliberately-planted edge cases

Each item below maps to a Tank feature it stresses:

| Planted | Tests |
| --- | --- |
| `AKIAIOSFODNN7EXAMPLE` in `seeds/leaked-key-example.md` | `secret_token` detection + one-way hash |
| Slack token `xoxb-1234567890-ABCDEFGHIJ` | `secret_token` via SlackDetector |
| `999988887777` near "AWS account" context | `aws_account_id` rule |
| `arn:aws:s3:::helix-prod-logs` in multiple docs | ARN regex + placeholder reuse |
| `payments.helix.internal` in 4+ docs | placeholder reuse across documents |
| CODEOWNERS says Marcus owns payments-api; CMDB says Sam | contradiction-surfacing nudge |
| Postmortem references a deleted runbook | stale_context nudge |
| `webhook-router` has a postmortem (INC-2025-0047) + Sigma rule (SSRF) | cross-service coverage exercised |
| Diana (SRE) mentioned in several docs but never has a dedicated entity card | pattern_detection nudge |
| One CMDB row lacks `owner_email` | data-quality flag |
| `priya.shah@helixrobotics.com` repeated in 6+ artifacts | email placeholder reuse |
| Mixed criticality labels (CMDB "critical" vs runbook "tier-2") | contradiction-surfacing |
| analytics-cross-account-role.json: 3 planted findings (HELIX-2098/2099/2100) | IAM audit report |
| k8s-rbac-pii-vault.yaml: `secrets/get` cluster-wide (HELIX-2101) | IAM audit, K8s RBAC parser |
| HELIX-2031: analytics-pipeline uses static Snowflake creds | exception tracking in secrets policy |
| HELIX-2108: identity-prod-pg uses password auth, not IAM auth | deferred_fix decision; threat model |
| HELIX-2095: break-glass alerts not automated (MANUAL ONLY) | accepted_risk; DFD threat T002 |
| HELIX-1822: webhook-router SSRF, no private IP blocking | accepted_risk decision; Sigma rule |
| 2 decisions with near-term `expires_at` | `decision_expiring` nudge fires within days |
| 10 unconfirmed glossary terms | glossary confirmation UX + nudge |
| Tabletop attack path: assume-role → bulk S3 GET → RDS drop | tabletop lessons capture |

## Open issues cross-referenced across the sample data

| ID | Summary | Where referenced |
| --- | --- | --- |
| HELIX-1822 | webhook-router SSRF, no private IP block | `webhook-router-dfd.mmd`, `helix-ec2-metadata-ssrf.yml`, decisions |
| HELIX-2031 | analytics-pipeline static Snowflake creds | `secrets-management.md` (exemption) |
| HELIX-2095 | break-glass audit alerts not automated | `06-pii-vault-detail.md`, `pii-vault-dfd.mmd` |
| HELIX-2098 | `rds:Describe*` on `Resource: "*"` | `analytics-cross-account-role.json` |
| HELIX-2099 | `rds-db:connect` not scoped to instance ARN | `analytics-cross-account-role.json` |
| HELIX-2100 | `s3:ListAllMyBuckets` in analytics role | `analytics-cross-account-role.json` |
| HELIX-2101 | pii-vault K8s RBAC `secrets/get` cluster-wide | `k8s-rbac-pii-vault.yaml` |
| HELIX-2108 | identity-prod-pg uses password auth, not IAM | `05-identity-svc-detail.md`, `identity-svc-dfd.mmd`, decisions |
| HELIX-2110 | no JWKS key revocation endpoint | `05-identity-svc-detail.md` |
| INC-2025-0047 | S3 pre-signed URL TTL was 7 days | `2025-11-device-cert-exposure.md`, `webhook-router-dfd.mmd` |

## How the loader categorizes files

| Subdirectory | DocumentCategory |
| --- | --- |
| `architecture/` | `architecture` |
| `repos/*/` | `code` (single doc per repo, summarized — not file-by-file) |
| `cmdb/*.csv`, `cmdb/*.json` | `cmdb` |
| `detections/*.yml` | `architecture` (Sigma rules, auto-detected) |
| `iam/*.json`, `iam/*.yaml` | `cmdb` (IAM/RBAC policies, content-sniffed) |
| `people/`, `policies/`, `runbooks/`, `postmortems/`, `seeds/`, `compliance/` | `people_process` |
| `dfd/` | **not ingested** — upload `.mmd` files manually via the DFD tool |

## Verification spot-checks after running both scripts

1. `GET /dfd` → upload `sample_data/dfd/payments-api-dfd.mmd` → Stage 3 workspace shows ~10 threat cards with CVSS estimates (or loads from cache instantly)
2. `GET /dfd` → pre-seeded "payments-api" entry shows a cache badge (no API call)
3. `GET /reports` → generate "IAM Audit" → finds analytics cross-account role as a finding
4. `GET /reports` → generate "Threat Landscape" for `identity-svc` → references HELIX-2108
5. `GET /reports` → generate "ATT&CK Mapping" → shows T1552.005, T1530, T1552.001
6. `GET /compliance` → shows SOC 2 + NIST CSF side-by-side; gap analysis highlights controls with no evidence
7. `GET /decisions` → 4 decisions shown; 2 expire soon (triggers `decision_expiring` nudge)
8. `GET /glossary` → 10 unconfirmed terms ready for confirmation
9. `GET /lessons` → 5 lessons searchable by tag (`vault`, `pii`, `gdpr`, etc.)
10. `GET /projects` → 4 projects in 3 teams visible on card grid
11. Chat: "What are the main risks in pii-vault?" → pulls from architecture doc + DFD + decisions
12. Chat tool `find_iam_risks` → returns analytics cross-account role as high-risk
13. Chat tool `find_detection_for_technique("T1530")` → returns `helix-s3-bulk-download.yml`

## Safety

- Every fake email uses `@helixrobotics.com` — not a real domain.
- Every fake AWS account ID is the AWS-published documentation example
  (`999988887777`, `888877776666`).
- Every fake AWS access key is `AKIAIOSFODNN7EXAMPLE` — the AWS docs
  test key.
- No real customer names, no real service URLs, no real people.

If you want to point Tank at your actual employer, **wipe this sample data
first** (`rm -rf sample_data/`) and re-set `TANK_INTERNAL_TLD` in
`.env` to your real internal TLD.
