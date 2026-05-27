# Features

Per-feature reference. Grouped by the phase that shipped them — this
matches how `HISTORY.md` tells the story and how the code is laid out.

## Core (Phase 1-11)

Reference for these lives in [architecture.md](../architecture.md);
no per-feature doc.

- **Onboarding** — see [first-run.md](../first-run.md).
- **Ingest pipeline** — see [architecture.md § subsystems](../architecture.md#1-ingest-pipeline-appingest).
- **Knowledge graph** — entities + relationships + provenance badges.
- **Chat + 6 original reports** — see [chat-and-reports.md](chat-and-reports.md).
- **Partner mode** — digest, journal, follow-ups, anniversary,
  meeting prep, notes-to-KB diff.
- **Opt-in connectors** — folder watcher, ICS calendar, CVE feed,
  GitHub poller (Phase 11). Configured in Settings → Integrations.

## Phase 12 — Threat models become living

- [threat-models-decisions.md](threat-models-decisions.md) — versioned
  threat models with drift detection + the decisions / accepted-risk log.

## Phase 13 — Security workstreams

- [workstreams.md](workstreams.md) — design reviews, postmortems,
  tabletops, on-call handoff brief, weekly security digest.

## Phase 14 — Coverage + visibility

- [coverage-visibility.md](coverage-visibility.md) — Sigma detection
  rules, ATT&CK mapping, compliance evidence collection, IAM policy
  translator + audit, attack-surface ledger.

## Phase 15 — Continuous learning + memory

- [second-brain.md](second-brain.md) — lessons-learned DB, glossary
  builder, personal ownership dashboard, security philosophy doc,
  security-focused anniversary retros.

## Update batch (2.1 / 2.2 / 2.3 / 3.1 / 3.2 / 3.3 / 3.4)

- **2.1** — Markdown rendering in all report detail pages (`marked.js`); PDF
  export via `window.print()` with print stylesheet; Markdown file download.
- **2.2** — Token cost counter fix: `cache_read_in` / `cache_create_in` columns
  added to `reports` table; new `api_calls` table captures all previously
  untracked Claude calls; `/api/usage/cost` now aggregates from three tables.
  `TANK_DEBUG_TOKENS=1` logs per-call token counts to console.
- **2.3** — Claude API optimization: entity extraction, meeting prep,
  journal/lesson extraction, and nudge question-of-week switched to
  `claude-haiku-4-5-20251001` (~10× cheaper for structured extraction).
- **3.1** — App redesign: flat topbar nav replaced with a grouped left sidebar
  (Workspace / Pipeline / Workstreams / System). Empty states added on first
  load. Cost badge moved to sidebar footer.
- **3.2** — [dfd-analysis.md](dfd-analysis.md) — STRIDE threat modeling for
  Data Flow Diagrams: 4-mode input, 4-step SSE progress tracker, split-panel
  interactive workspace, threat cards with CVSS + OWASP/CWE references, and
  4 export formats (PDF, annotated `.mmd`, original `.mmd`, JSON).
- **3.3** — [projects.md](projects.md) — project dashboard with color/notes
  fields, detail page, last-opened memory, and project-scoped chat context.
- **3.4** — Sample data expansion: 16 new fixture files covering service-level
  architecture docs, 3 additional Sigma rules (T1552.005/T1530/T1552.001),
  over-broad IAM policies with planted findings, NIST CSF 2.0 compliance
  framework, a PII breach runbook, and a postmortem for webhook-router. Plus
  `scripts/seed_db.py` — an idempotent DB seed script that populates org/team/
  project hierarchy, pre-cached DFD analyses (18 STRIDE threats across 2 services),
  4 decisions, 10 glossary terms, 5 lessons, 1 tabletop, 3 journal entries, and
  3 follow-ups. Exercises every living-artifact feature with no API cost.
