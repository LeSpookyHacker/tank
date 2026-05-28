# Discover — Intake Interview, Org Discovery Wizard, Security Stack Audit

The **Discover** group in the left nav covers the three features you use before and
during the first two weeks: building a skeleton knowledge graph from conversations and
org scans, before any documents are uploaded.

---

## Intake Interview (`/intake`)

The front door for new users. A one-question-at-a-time conversational flow that takes
about 15 minutes and produces a Day-1 Brief with no documents required.

### When it runs

- **First time:** launches automatically after the setup screen and redirects new users
  before they reach the dashboard. The first 5 questions are required; the remaining 15
  can be deferred.
- **"Complete your setup" banner:** if you skipped or didn't finish, a non-blocking
  banner on the home dashboard links back to `/intake`. Dismissible; re-appears after
  7 days.
- **On demand:** accessible from the left nav (Discover → Intake Interview) or
  Settings → Organization → Re-run intake interview at any time.

### The 20 questions

| # | Question | Seeds |
|---|----------|-------|
| 1 | What does your company build? | Org profile |
| 2 | Who are your customers? | Org profile — customer type |
| 3 | What sensitive data does the company handle? | `Asset` stubs (PII, payment data, health data…) |
| 4 | What cloud providers does the company use? | `CloudAccount` stubs |
| 5 ★ | Names of your most important services/applications | `Service` entity stubs |
| 6 | Who owns those services? | `Person` / team stubs |
| 7 | How large is the engineering org? | Org profile — team size |
| 8 | Does the company have an identity provider? | `Asset` stub (kind: identity_provider) |
| 9 | Is MFA enforced for internal systems? | Risk hypothesis input |
| 10 | Does the company have a secrets manager? | `Asset` stub if yes |
| 11 | Are there any existing security tools? | `Asset` stubs (kind: security_tool) |
| 12 | Has the company ever had a security incident? | Risk hypothesis input |
| 13 | Any existing compliance requirement? | `compliance_targets` on org profile |
| 14 | Do enterprise customers require compliance evidence? | Org profile |
| 15 | Primary programming language or stack? | Org profile |
| 16 | Where does the company's code live? | Org profile |
| 17 | Does the company have a staging/production separation? | Risk hypothesis input |
| 18 | Is there a disaster recovery / backup process? | Risk hypothesis input |
| 19 ★ | What does leadership expect from you in the first 90 days? | 90-Day Plan priorities |
| 20 ★ | What are you most worried about security-wise right now? | Initial risk hypothesis |

★ Most impactful for Day-1 Brief quality. Questions 1–5 are required.

### Entity stubs

Every named entity from your answers is created with:
- `confidence: 0.3` (low — self-reported, unverified)
- `provenance: user`
- `attrs.stub_source: intake_interview`

Stubs appear with a dashed border in the entity browser. Confidence rises as ingested
documents confirm the entity.

### The Day-1 Brief

Generated in the background immediately after you submit. Available in **Reports**
(`/reports`, kind = `day1_brief`). Four sections:

1. **What I know** — summary of your company from the interview answers.
2. **Top probable risk areas** — 3 risks derived from your company profile (e.g.
   payment data + no WAF = payment surface risk). Marked as preliminary.
3. **Who to meet in week 1** — specific people/teams with a suggested question each.
4. **What I don't know yet** — explicit list of 5–8 investigation items Tank couldn't
   determine from the interview. This is the most actionable section.

The brief regenerates on demand — a "Regenerate brief" button appears in Reports and on
the home dashboard at Day 14.

---

## Org Discovery Wizard (`/discovery`)

A guided 4-step workflow to systematically discover what exists in your org. Accessible
from the left nav, the post-intake completion screen, and the entity browser empty state.

### Step 1 — GitHub org scan

Connect a GitHub personal access token (read-only, `repo` scope). Tank enumerates all
repositories in the org and displays them as a checklist.

Each repo shows: name, description, primary language, last commit date, visibility
(public/private). Tank pre-checks repos that look like production services using this
heuristic:
- Not archived
- Committed within the last 90 days
- Name doesn't end with `-docs`, `-config`, `-terraform`, `-infra`, `-scripts`, `-ci`

Per-repo action: **Ingest** (adds to ingestion queue), **Note only** (creates a
`Repo` entity stub without ingesting), or **Skip**.

For checked repos that you mark "Ingest": Tank adds them to the document ingestion queue.

### Step 2 — Team directory import

Upload a CSV with columns: `name`, `email`, `team`, `role`. Tank shows a preview with
editable team name cells (so you can rename and merge duplicates before confirming).

On confirm: creates `Person` entity stubs for each person and `Person` entity stubs
tagged `kind: team` for each unique team name, all with `provenance: user` and
`source: directory_import`.

### Step 3 — Manual service entry

A structured form for services you've discovered in conversations that aren't in a
repository. Fields: service name, type (web app / API / mobile / data store /
infrastructure / internal tool / third-party), owning team (from your team stubs),
tech stack (freetext), notes.

"Add another" keeps you in the form until you've captured everything you know.

### Step 4 — Summary and confirm

Shows counts: repos selected, people, teams, manual services. On confirm, Tank creates
all entity stubs and shows links to the entity browser and the ingestion UI with the
queue pre-loaded.

---

## Security Stack Audit (`/stack-audit`)

A structured inventory of your security tooling across 15 capability categories.
One row per category, inline-editable in the browser.

### The 15 categories

| # | Category |
|---|----------|
| 1 | Identity Provider (SSO/LDAP) |
| 2 | Multi-Factor Authentication |
| 3 | Secrets Management |
| 4 | SIEM / Log Aggregation |
| 5 | Web Application Firewall (WAF) |
| 6 | Endpoint Detection & Response (EDR) |
| 7 | Vulnerability Scanner |
| 8 | Data Loss Prevention (DLP) |
| 9 | Network Segmentation |
| 10 | Backup & Recovery |
| 11 | Patch Management |
| 12 | Security Training Platform |
| 13 | Bug Bounty / Penetration Testing |
| 14 | Container / Supply Chain Security |
| 15 | Cloud Security Posture Management (CSPM) |

### Per-category fields

- **Current tool** — tool name, or leave blank for "None"
- **Deployment status** — `None` / `Partial` / `Full`
- **Coverage notes** — what's in scope
- **Known gaps** — what's missing

### How it's used

- **Completion percentage** is shown on the Security Program Dashboard as a panel.
- **The Prioritization Engine** uses deployment status when computing risk scores:
  categories marked `None` with no compensating control cause affected service risks
  to score higher.
- **A weekly nudge** fires during the Discovery phase (tenure days 1–14) until
  completion reaches 80%.

The audit is saved as a single record per org, updated in place. There's no version
history — it's a living snapshot of your current tooling landscape.
