# First run — onboarding and the intake interview

Tank's first-run flow has two stages: a brief setup screen (role + cadence), then the
**intake interview** — 20 questions about your company that take about 15 minutes and
require no uploaded documents. By the end you have a skeleton knowledge graph and a
Day-1 Brief.

---

## Stage 1 — Setup screen

After the server first loads, Tank asks for two things:

- **Your role** — Staff IC, Manager, or Both. Sets the framing for chat replies and
  reports. You can change this later in Settings.
- **Daily digest time** — when the morning brief fires (default 08:00).

Hit **Finish setup** and Tank redirects you to the intake interview.

---

## Stage 2 — The intake interview (`/intake`)

The interview is a one-question-at-a-time conversational flow. You don't need anything
prepared — answer from memory; estimates and guesses are fine. Tank marks everything
from this interview as low-confidence and refines it as you ingest documents later.

### The 20 questions

| # | Question | What it seeds |
|---|----------|---------------|
| 1 | What does your company build? | Org profile description |
| 2 | Who are your customers? | Customer type on org profile |
| 3 | What sensitive data does the company handle? | `Asset` stubs (PII, payment data, health data…) |
| 4 | What cloud providers does the company use? | `CloudAccount` stubs (AWS, GCP, Azure…) |
| 5 | Names of your most important services or applications | `Service` entity stubs |
| 6 | Who owns those services? | `Person` / team stubs |
| 7 | How large is the engineering org? | Org profile team size |
| 8 | Does the company have an identity provider (Okta, Google Workspace…)? | `Asset` stub (identity_provider) |
| 9 | Is MFA enforced for internal systems? | Org profile (used in risk hypothesis) |
| 10 | Does the company have a secrets manager (Vault, AWS Secrets Manager…)? | `Asset` stub if yes |
| 11 | Are there any existing security tools in place? | `Asset` stubs (security_tool) |
| 12 | Has the company ever had a security incident or breach? | Org profile (seeds risk hypothesis) |
| 13 | Is there any existing compliance requirement? | `compliance_targets` on org profile |
| 14 | Do enterprise customers require compliance evidence? | Org profile |
| 15 | Primary programming language or stack? | Org profile |
| 16 | Where does the company's code live? | Org profile |
| 17 | Does the company have a staging/production separation? | Org profile |
| 18 | Is there a disaster recovery / backup process? | Org profile |
| 19 | What does leadership expect from you in the first 90 days? | Seeds 90-Day Plan priorities |
| 20 | What are you most worried about security-wise right now? | Seeds initial risk hypothesis |

Questions 1–5 are required (Tank can't generate a useful Day-1 Brief without them).
Questions 6–20 can be skipped and answered later.

### Entity stubs

Every named entity extracted from your answers (a service, a team, a tool, a cloud
provider) becomes an **entity stub** — a graph node created with:

- `confidence: 0.3` (low — self-reported, not yet verified by ingested documents)
- `provenance: user`
- `attrs.stub_source: intake_interview`

Stubs appear with a dashed border in the entity browser to distinguish them from
confirmed (ingested) entities. As you ingest documents that mention the same service or
team, the confidence score rises and the stub becomes a full entity.

---

## Stage 3 — What happens after you submit

Two things run in the background immediately:

**Entity seeding** — all named services, teams, tools, cloud providers, and data types
from your answers are created as entity stubs in the knowledge graph. This takes a few
seconds.

**Day-1 Brief generation** — Tank calls `claude-sonnet-4-6` with your intake answers
and generates a four-section brief:

1. **What I know** — a summary of your company from the interview answers.
2. **Top probable risk areas** — 3 risks derived from your company profile (e.g.
   payment data + no WAF → payment surface risk). Marked as preliminary.
3. **Who to meet in week 1** — specific people and teams from your answers, with a
   suggested question for each.
4. **What I don't know yet** — an explicit list of 5–8 gaps Tank couldn't determine
   from the interview alone. This is the most important section — it's your
   investigation list for weeks 1–2.

The brief appears in **Reports** (`/reports`) under `kind = day1_brief`. It also
appears as a link on the post-interview completion screen.

---

## Stage 4 — The "You're set up" completion screen

After submitting the interview, Tank shows:

- A link to your Day-1 Brief (available in Reports once generation completes, usually
  under a minute)
- A link to the Entity Graph (`/entities`) — your skeleton knowledge graph is ready
- A "What to do next" card pointing to the **Org Discovery Wizard** (`/discovery`)

---

## What to do next

The intake interview gives you a starting point. Three things to do immediately after:

1. **Open the Org Discovery Wizard** (`/discovery`) — connect your GitHub token to
   enumerate repos, import your team directory from a CSV, and manually add services
   you've discovered in conversations.

2. **Complete the Security Stack Audit** (`/stack-audit`) — 15 capability categories
   (identity provider, MFA, secrets manager, SIEM, WAF, EDR…). This feeds the
   Prioritization Engine.

3. **Start ingesting documents** (`/ingest`) — any architecture docs, Terraform
   configs, runbooks, or org charts you can access. Each one enriches the entity graph
   and makes chat, threat models, and reports more specific to your environment.

See [discover.md](features/discover.md) for full coverage of all three Discover-group
features.

---

## Returning users — re-running the intake interview

The intake interview is accessible at any time from `/intake`. Re-running it creates a
new interview record (previous answers are preserved) and re-seeds the entity graph
with any new information you provide.

You can also access it from: **Settings → Organization → Re-run intake interview**.

To fully reset Tank (wipe all data and start over):

1. Settings → "Wipe everything" (you must type `delete tank` to confirm).
2. Or: `rm ~/.tank/db.sqlite` and restart Tank.

The wipe clears your KB, decisions, threat models, lessons, and philosophy doc. Your
`~/.tank/backups/` directory is **not** touched by the wipe — weekly SQLite snapshots
are kept there for 8 weeks.
