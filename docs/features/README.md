# Feature reference

Per-feature documentation, organized by the left nav group where each feature lives.
For day-to-day workflow guidance (how to use these features together), see
[using-tank.md](../using-tank.md).

---

## Discover

Everything you use in the first two weeks to build your initial picture of the org —
before you have documents.

- [discover.md](discover.md) — **Intake Interview**, **Org Discovery Wizard**,
  **Security Stack Audit**

---

## Analyze

Tools for reasoning about what you've found.

- [chat-and-reports.md](chat-and-reports.md) — **Chat** (streaming with 15 tools,
  discovery mode, mode selector) + **14+ report kinds** (threat landscape, cross-service
  gaps, state of security, initial assessment, program roadmap, and more)
- [dfd-analysis.md](dfd-analysis.md) — **DFD Threat Modeling** (4-mode input, SSE
  progress, split-panel workspace, STRIDE + CVSS, PDF export)
- [threat-models-decisions.md](threat-models-decisions.md) — **Living Threat Models**
  (versioned, drift-aware) + **Decisions Log** (design choices, accepted risks,
  deferred fixes, security invariants)
- [workstreams.md](workstreams.md) — **Design Reviews** (freewrite → checklist →
  approval)

---

## Track

Operational tracking of findings, decisions, and incidents.

- [security-program.md](security-program.md) — **Risk Register**, **Security Program
  Dashboard** (6-domain KPIs, executive brief, 12-week trends), **IR Runbooks**
- [build.md](build.md#vulnerability-triage-vulnerabilities) — **Vulnerability Triage**
  (triage queue, assign, close, promote to risk register)
- [threat-models-decisions.md](threat-models-decisions.md) — **Decisions Log**
- [workstreams.md](workstreams.md) — **Postmortems**, **Tabletops**

---

## Build

Generating security artifacts and structured plans.

- [build.md](build.md) — **Security Policies** (5 first-draft policies from KB context),
  **90-Day Plan** (week-by-week task list from intake answers), **Vulnerability Triage**,
  **Prioritization Engine** (concrete top-5 quarterly action plan),
  **Compliance Framework Wizard** (8-question → framework recommendation)
- [security-program.md](security-program.md) — **IR Runbooks** (per-service, per-scenario
  5-phase incident-response playbooks)

---

## Report

Reports and program-level visibility.

- [chat-and-reports.md](chat-and-reports.md) — all report kinds including the three new
  leadership reports (`state_of_security`, `initial_assessment`, `program_roadmap`)
- [security-program.md](security-program.md) — **Security Program Dashboard**
- [coverage-visibility.md](coverage-visibility.md) — **Detection coverage** (Sigma/ATT&CK),
  **IAM policy translator**, **Compliance evidence**, **Attack-surface ledger**

---

## Knowledge

The living knowledge base and memory layer.

- [concepts.md](../concepts.md) — **Entity Graph** (14 entity types, 9 relationship
  kinds, provenance badges, entity stubs)
- [second-brain.md](second-brain.md) — **Lessons-learned DB**, **Glossary builder**,
  **Personal ownership dashboard**, **Security philosophy doc**
- [projects.md](projects.md) — **Projects** (scoped workspaces, starter templates,
  project-scoped chat)

---

## Partner mode

The daily companion: digest, nudges, journal, meeting prep, anniversaries.

- [using-tank.md](../using-tank.md) — day-to-day workflows that tie all features together
- [workstreams.md](workstreams.md) — pre-meeting briefs, weekly security digest,
  on-call handoff brief

---

## Historical reference

<details>
<summary>Version batch notes (click to expand)</summary>

- **2.1** — Markdown rendering + PDF export via print stylesheet in all report pages.
- **2.2** — Token cost counter: `cache_read_in` / `cache_create_in` added to `reports`
  table; `api_calls` table for untracked Claude calls; three-source cost aggregation.
- **2.3** — Entity extraction, meeting prep, journal/lesson extraction, nudge
  question-of-week switched to `claude-haiku-4-5-20251001` (~10× cheaper).
- **3.1** — App redesign: flat topbar nav replaced with grouped left sidebar.
- **3.2** — DFD threat modeling (4-mode input, SSE progress, split-panel workspace,
  STRIDE + CVSS, 4 export formats).
- **3.3** — Projects dashboard with color/notes fields, detail page, project-scoped chat.
- **3.4** — Sample data expansion: 16 new fixture files, `scripts/seed_db.py`.
- **Redesign** — First-hire pivot: intake interview, org discovery wizard, security
  stack audit, chat discovery mode, vulnerability triage, policy scaffolding, 90-day
  plan, prioritization engine, compliance wizard, persistent left nav.

</details>
