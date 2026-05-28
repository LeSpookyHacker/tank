# Build — Policies, 90-Day Plan, Vulnerability Triage, Prioritization, Compliance Wizard

The **Build** and **Track** nav groups cover the features for the Foundation phase
(Days 30–60): generating starting-point security artifacts, tracking and triaging
findings operationally, and producing the prioritization and compliance guidance that
turns a list of problems into an action plan.

---

## Security Policies (`/policies`)

Five first-draft security policies generated from your KB context and org profile.
These are starting points you own and edit — not templates with placeholders.

### The five policies

| Kind | Display name |
|------|-------------|
| `acceptable_use` | Acceptable Use Policy |
| `incident_response` | Incident Response Policy |
| `secure_sdl` | Secure Development Lifecycle (SDL) Policy |
| `vulnerability_management` | Vulnerability Management Policy |
| `data_classification` | Data Classification Policy |

### Generation

Click **Generate →** next to any policy. Tank shows a pre-generation summary ("I'll
generate this using your company context: N services, cloud providers, compliance
target SOC 2…"), then generates using `claude-sonnet-4-6` with your entity graph and
org profile as context.

What makes the output specific:
- Service names come from the entity graph (e.g., "Payments API" not "[service name]")
- Cloud provider is taken from your `CloudAccount` entities
- Authentication system comes from your identity provider entity stub
- Data types come from `Asset` entities tagged `kind: data_type`
- Compliance obligations come from `compliance_targets` on the org profile

### Editing

Policies open in an inline editor with two views:
- **Rendered** — markdown rendered for reading
- **Edit Markdown** — raw markdown textarea with a Save button

Click **Mark reviewed** to advance from `draft` → `reviewed`, then **Mark approved**
to reach `approved`.

### Storage

Each policy is stored as a `policy_artifact` row. Regenerating bumps the version
number. All versions are retained. Status: `draft` → `reviewed` → `approved`.

### Post-generation

After generation, Tank creates draft decisions log entries for the implicit design
choices in the policy (e.g., "Minimum password length: 12 characters" → a
`design_choice` decision entry). You confirm or edit these in the Decisions Log.

---

## 90-Day Plan (`/plan`)

A week-by-week task list for weeks 1–13, generated from your intake answers and entity
graph and tailored to your specific company. Not a generic template.

### Generation

Click **Generate plan**. Tank uses:
- Your intake interview answers (especially Q19 — leadership expectations, Q20 — top
  worries)
- The entity graph (actual service names, team names, compliance targets)
- Standard first-hire milestones

Generation takes ~30 seconds. Refresh the page after.

### Task structure

Each task has:

| Field | Example |
|-------|---------|
| Week | 2 |
| Title | "Run threat model for Payments API" |
| Description | 2-3 sentences of context |
| Why it matters | One sentence |
| Done condition | "Threat model completed with at least 5 STRIDE findings" |
| Source | `intake` / `kb_state` / `compliance` / `milestone` |

### Checking off tasks

Click the checkbox on any task to mark it done. For some tasks, Tank can auto-detect
completion — for example, "Generate threat model for [service]" marks itself done
when a threat model for that service entity exists in the DB.

### Home dashboard integration

The current week's 3–5 tasks appear in a "This week" card on the home dashboard.
Click through to the full plan.

### Regeneration

A **Regenerate plan** button is always available. A monthly nudge fires when the plan
hasn't been regenerated in 30+ days or when the week's tasks are all checked off.

---

## Vulnerability Triage (`/vulnerabilities`)

A triage queue for the vulnerabilities table — CVEs from the feed watcher, scanner
findings, and manual entries. Distinct from the risk register: this is operational
vulnerability tracking, not strategic risk management.

### The triage queue

Shows all vulnerabilities with `triage_status = new` (or `status = open`), sorted by
severity (critical first), then by discovery date.

Each item shows: CVE ID (if applicable), title, severity badge, source (nvd /
github_dependabot / scanner / manual), and affected service names from the entity
graph.

### Actions

**Triage** — confirm or reassess severity; moves status to `triaged`. Use this when
you've reviewed the finding and validated it applies to your environment.

**Assign** — set an owner (freetext name or team name) and an optional due date; moves
status to `in_remediation`. Sends the finding to the owner's queue.

**Close** — mark as one of: `patched` (remediated), `accepted` (risk accepted with
rationale), or `wont_fix` (out of scope / insufficient risk). For `accepted`: you're
prompted to enter a rationale that's stored with the record.

**→ Risk Register** — appears on high/critical items. Promotes the vulnerability to a
risk register entry so it's tracked at the strategic level alongside accepted risks and
design choices.

### Program Dashboard integration

The Security Program Dashboard (`/security-program`) shows:
- Open vulnerability count broken down by severity
- Mean-time-to-close (rolling 90-day average)
- A "vulnerability aging" indicator (how long items have been in triage)

### Nudges

- Weekly nudge if the triage queue has items older than 7 days: "You have N untriaged
  vulnerabilities. [Review queue →]"
- Day-45 nudge if no vulnerability management process has been started:
  "Foundation phase: set up your vulnerability management process."

---

## Prioritization Engine (from `/security-program`)

Given a risk register with N items across M services, what do you fix first? The
Prioritization Engine produces a concrete, opinionated top-5 quarterly action plan.

### How to run it

Navigate to **Security Program Dashboard** (`/security-program`) and click
**Generate priorities**. Generation runs in the background (~30 seconds) and stores
the result as a report with `kind = prioritization`.

### Inputs

The engine uses all of the following as context for the Claude call:

- Risk register (all open entries with inherent/residual scores and treatment)
- Entity graph (service criticality, data types handled, team ownership)
- Security Stack Audit (which compensating controls exist)
- Compliance targets (regulatory exposure increases rank)
- Open vulnerability triage queue (open high/critical CVEs)

### Output format

Top 5 items, each with:

| Field | Description |
|-------|-------------|
| Rank | 1–5 |
| Title | Short risk description |
| Scope | Affected service or area |
| Why it's #N | One plain-language sentence (not a CVSS score) |
| Done condition | Specific, testable outcome |
| Effort | Days / Weeks / Months |
| Owner | From entity graph service ownership |

The engine is prompted to be opinionated — it cannot hedge into "it depends." If it's
uncertain between two items, it picks the higher-risk one and explains why.

### Caching and regeneration

The output is cached and displayed with a "Generated [date]" label. Click **Regenerate**
to refresh. A monthly nudge fires when the output is 30+ days old: "Your
prioritization is stale. [Refresh your top 5 →]"

---

## Compliance Framework Wizard (`/compliance/wizard`)

An 8-question decision tree that recommends the right compliance framework for your
company. Accessed from **Compliance** in the left nav → "Compliance Framework Wizard."

### The 8 questions

1. What industry does the company operate in?
2. Who are the primary customers?
3. Does the company handle payment card data?
4. Does the company handle health or medical information?
5. Do any customers require a specific compliance attestation as a contract condition?
6. Does the company have investors or a board asking about compliance?
7. Does the company sell to US federal government or handle government data?
8. What is the company's realistic timeline for initial compliance?

### Output

A ranked recommendation for the top 2 frameworks. For each:

- **Which framework and why** — 2-3 sentences in business language (not standards jargon)
- **Honest effort estimate** — rough engineer-months for initial compliance, major
  milestones, common blockers
- **Gap analysis** — based on your current KB state, what are the biggest gaps between
  where you are and this framework's requirements
- **Realistic timeline** — adjusted to your stated capacity

### Storing the recommendation

The top recommendation is automatically stored as a `design_choice` entry in the
**Decisions Log** with title "Compliance framework selection: [framework]". This
creates an audit trail for when and why you chose your compliance path.

The full recommendation text is also available in **Reports** (`/reports`,
kind = `compliance_recommendation`).
