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
