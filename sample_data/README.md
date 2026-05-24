# Helix Robotics — Tank Sample Data

A synthetic corpus that simulates **what a new Sr/Staff/Manager Security
Engineer might be handed in their first week** at a mid-size B2B SaaS
company called Helix Robotics. None of this is real. All hostnames,
emails, account IDs, secrets, and people are fabricated.

Use this corpus to:

- Smoke-test Tank's ingestion pipeline (every parser type is exercised).
- Watch the redaction layer turn cleartext into placeholders.
- Build a knowledge graph you can chat with.
- Generate the six onboarding reports against realistic-looking inputs.
- Trigger the partner-mode nudges (coverage gaps, contradictions,
  pattern detection).

## Quickstart

Load the entire corpus with:

```bash
python -m scripts.load_fixtures
```

To preview what would be ingested without touching the API:

```bash
python -m scripts.load_fixtures --dry-run
```

## Scenario

You've just joined **Helix Robotics** as the second Security Engineer
(the first is Diana Okoro on Detection & Response). Helix is ~80 people,
Series B (Q3 2025), processing payments and identity for robotics OEMs.
Your scope as a new hire is loosely defined — somewhere between AppSec,
Cloud Sec, and "general security plumbing" — and you'll spend the next
30/60/90 days figuring out what matters.

Helix's HQ is Austin; satellites in Seattle and Lisbon. The internal
TLD is `helix.internal`. AWS prod account is `999988887777`, staging
`888877776666`, region `us-west-2`.

## What's here

```
sample_data/
├── company.md                                # 1-page overview
├── architecture/                             # high-level system docs
│   ├── 01-platform-overview.md               # → PDF via _gen_fixtures
│   ├── 02-auth-flow.md                       # → PNG via _gen_fixtures
│   ├── 03-data-flow.md                       # mermaid + prose
│   └── 04-region-map.md                      # AWS accounts, regions
├── repos/
│   ├── payments-api/                         # Python FastAPI repo
│   └── webhook-router/                       # Go service
├── cmdb/
│   ├── services.csv                          # 8 services + owners
│   └── cloud-accounts.csv                    # AWS accounts
├── people/
│   ├── org-chart.md                          # engineering org tree
│   ├── on-call.csv                           # rotations
│   └── 1-1-cadence.md                        # who 1:1s with whom
├── policies/
│   ├── access-policy.md                      # → DOCX via _gen_fixtures
│   ├── incident-response.md
│   └── data-classification.md
├── runbooks/
│   ├── service-restart.md
│   ├── rotate-customer-api-key.md
│   └── investigate-suspicious-login.md
├── postmortems/
│   ├── 2026-02-payments-outage.md
│   └── 2026-04-credential-leak-close-call.md
├── seeds/                                    # planted to test redaction
│   ├── leaked-key-example.md                 # fake AKIA + Slack token
│   └── internal-host-list.md                 # internal hosts + IPs
├── detections/                               # Sigma rules (auto-detected)
│   └── helix-suspicious-login.yml
├── iam/                                      # IAM policies (auto-detected)
│   └── prod-s3-policy.json
└── compliance/                               # Control frameworks (auto-detected)
    └── controls-soc2.json
```

## Parser coverage

Every parser type Tank ships is exercised by this sample data:

| Parser | Sample file(s) | How dispatched |
| --- | --- | --- |
| MarkdownParser | `architecture/*.md`, `policies/*.md`, etc. | extension `.md` |
| PDFParser | `architecture/01-platform-overview.pdf` | extension `.pdf` |
| DocxParser | `policies/access-policy.docx` | extension `.docx` |
| ImageParser (vision) | `architecture/02-auth-flow.png` | extension `.png` |
| CSVJSONParser | `cmdb/*.csv`, `people/on-call.csv` | extension `.csv` |
| Code summary | `repos/payments-api/`, `repos/webhook-router/` | directory walk |
| SigmaParser | `detections/helix-suspicious-login.yml` | content-sniff: `logsource`+`detection` |
| IAMParser | `iam/prod-s3-policy.json` | content-sniff: `Version`+`Statement` |
| ControlFrameworkParser | `compliance/controls-soc2.json` | content-sniff: `framework`+`controls` |

The PDF, DOCX, and PNG files are generated from their markdown sources by
`scripts/_gen_fixtures.py`. Run it once before ingesting:

```bash
python -m scripts._gen_fixtures
```

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
| `webhook-router` has no postmortem, no runbook, no policy mapping | cross-service gap report |
| Diana mentioned in 3 docs but never has a dedicated entity card | pattern_detection nudge |
| One CMDB row lacks `owner_email` | data-quality flag |
| `priya.shah@helixrobotics.com` repeated in 6+ artifacts | email placeholder reuse |
| Mixed criticality labels (CMDB "critical" vs runbook "tier-2") | future contradiction-surfacing |

## How the loader categorizes files

| Subdirectory | DocumentCategory |
| --- | --- |
| `architecture/`, `repos/*/README.md`, `repos/*/docs/*` | `architecture` |
| `repos/*/` (rest of tree) | `code` (single doc per repo, summarized) |
| `cmdb/*.csv`, `cmdb/*.json` | `cmdb` |
| `detections/*.yml` | `architecture` (Sigma rules, auto-detected) |
| `iam/*.json` | `cmdb` (IAM policies, auto-detected) |
| `people/`, `policies/`, `runbooks/`, `postmortems/`, `seeds/` | `people_process` |
| `compliance/*.json` | `people_process` (control frameworks, auto-detected) |

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
