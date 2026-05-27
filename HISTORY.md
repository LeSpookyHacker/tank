# Tank — build history

A running record of what was built, when, and why. Read this top-down
to understand the project's evolution. Each entry is a session's worth
of work, in chronological order.

> All sessions to date use Python 3.9 (system Python on the dev Mac).
> The plan targets 3.11+; Python 3.9 needs `eval_type_backport` for
> Pydantic union-syntax support, and disables `sqlite-vec` (the
> macOS-bundled sqlite3 module was compiled without
> `enable_load_extension`). The graceful-degradation paths work —
> FTS5 keyword search still functions; vector search falls back.

---

## 2026-05-26 — Comprehensive sample data expansion (3.4)

### Goal

The existing Helix Robotics fixture set (26 files + 2 repos) exercised the
ingest pipeline and redaction engine well, but left every living-artifact
feature untested — no org/team/project hierarchy, no DFD analyses, no
decisions log, no glossary, no lessons, no tabletop, no journal. The goal
was to build a **complete** sample dataset that exercises every Tank feature
before real-employer use.

### What got built

**Track A — 16 new files in `sample_data/`** (ingested by `load_fixtures.py`):

- `architecture/05-identity-svc-detail.md` — OIDC/OAuth2 internals, JWT
  signing (RS256 + Vault), Redis session store, RDS gap (HELIX-2108: password
  auth instead of IAM auth), JWKS cache gap (HELIX-2110), rate-limit gap (HELIX-2112).
- `architecture/06-pii-vault-detail.md` — mTLS-only inbound (payments-api sole
  caller, CN check at app layer), CMK-encrypted RDS (IAM auth, migrated 2024-Q4),
  isolated EKS node group ng-pii, no internet egress, break-glass two-person
  approval. Gap: break-glass audit not automated (HELIX-2095).
- `people/team-directory.csv` — 18-person roster across 5 teams (Platform
  Security, AppSec, Threat Intelligence, SRE, Data Engineering). Includes Mei
  Watanabe (start_date 2026-04-28, the "new hire" persona), Jordan Lee VP Eng,
  Tom Brandt CTO, Sara Goldstein CEO.
- `policies/secrets-management.md` — SEC-POL-003: Vault-dynamic requirement,
  rotation SLA table (8h dynamic / 30d PKI / 90d static), approval workflow,
  known exemption HELIX-2031 (analytics-pipeline Snowflake static creds).
- `runbooks/respond-to-pii-breach.md` — 6-step PII breach runbook: assemble,
  containment (scale down pii-vault, revoke mTLS cert, rotate Vault token, CMK
  rotation), scope assessment (Vault audit logs + CloudTrail RDS), notification
  timelines (GDPR 72h, OEM 24h), remediation, post-incident. Includes shell
  commands and SQL for scope assessment.
- `postmortems/2025-11-device-cert-exposure.md` — INC-2025-0047, P1. webhook-router
  set S3 pre-signed URL TTL to 7 days. 240 URLs generated in 6h window; no confirmed
  exfil. Fix: S3 Object Lock max 10min TTL. Closes the "no postmortem for
  webhook-router" gap in the original fixture set.
- `detections/helix-ec2-metadata-ssrf.yml` — Sigma rule: HTTP calls to
  169.254.169.254 from app processes. ATT&CK T1552.005. References HELIX-1822.
- `detections/helix-s3-bulk-download.yml` — Sigma rule: >500 S3 GetObject in
  5 minutes by non-automation principal. ATT&CK T1530.
- `detections/helix-vault-token-anomaly.yml` — Sigma rule: Vault auth success
  from IP outside known CIDRs. ATT&CK T1552.001.
- `iam/analytics-cross-account-role.json` — Cross-account IAM role (staging
  account 888877776666 assumes into prod 999988887777). Intentionally over-broad:
  three planted findings (HELIX-2098/2099/2100) for the IAM audit report.
- `iam/k8s-rbac-pii-vault.yaml` — K8s ServiceAccount + ClusterRole + ClusterRoleBinding
  + NetworkPolicy for pii-vault-sa. Mild over-permission: `secrets/get` is
  cluster-wide (HELIX-2101). Tests the YAML IAM parser path.
- `compliance/controls-nist-csf.json` — NIST CSF 2.0 fragment (8 controls across
  GV/ID/PR/DE functions) with `helix_implementation` and `gap` fields. Enables
  cross-framework gap analysis alongside the existing SOC 2 fixture.
- `dfd/payments-api-dfd.mmd` + `dfd/identity-svc-dfd.mmd` + `dfd/pii-vault-dfd.mmd`
  + `dfd/webhook-router-dfd.mmd` — four Mermaid DFD source files for manual upload
  into Stage 1 Tab B of the DFD tool. The `dfd/` directory is excluded from
  `load_fixtures.py` (not a pipeline-ingest target).

**Track B — `scripts/seed_db.py`** (idempotent, no API calls):

Seeds every living-artifact table through Tank's own store modules (same write
paths the app uses):

- Org: renames "My Organization" → "Helix Robotics".
- Teams: Platform Security (purple), AppSec (blue), Threat Intelligence (red).
- Projects: Auth Hardening Q2 2026 (high, active), PII Data Program (critical,
  active), Threat Model Coverage (medium, active), SOC 2 Evidence Sprint (medium,
  archived).
- DFD analyses: 2 pre-cached entries (`dfd_analyses` table) — payments-api (10
  STRIDE threats T001–T010, CVSS 3.1–9.8) and identity-svc (8 threats T001–T008).
  Both are marked `cached=1` so the Stage 3 workspace loads instantly without an
  API call.
- Decisions: 4 entries across all four `kind` values. Two have `expires_at` set
  within the next 36–67 days, which triggers the `decision_expiring` nudge on boot.
- Glossary: 10 terms, all `confirmed=False`, to exercise the confirmation UX.
- Lessons: 5 entries extracted from postmortem + design-review patterns, tagged
  across `vault`, `pii`, `s3`, `incident-response`, `gdpr`, `cmdb`, `oncall`.
- Tabletop: "Ransomware via compromised analytics pipeline" — 4 timed injects
  from AssumeRole anomaly (T+0) through ransom email (T+25m).
- Journal: 3 entries from Mei Watanabe's first weeks (2026-04-28, 2026-05-07,
  2026-05-19), inserted with historical `date_label` via direct DB write (bypasses
  the `upsert_for_today` constraint).
- Follow-ups: 3 entries due in 7/14/30 days — HELIX-2108 RDS IAM auth, HELIX-1822
  SSRF fix timeline, annual Stripe SOC 2 report.

**Documentation:**

- `sample_data/README.md` — complete rewrite: full file inventory with tree,
  parser coverage table (all 10 parser types now), living-artifacts seed table,
  edge-case table (now 17 planted items), open-issues cross-reference table,
  and 13-item verification spot-check checklist.
- Root `README.md` — sample data section updated: new counts, all three script
  steps, summary of what's included.
- `docs/installation.md` — 4-step sample data ingest section with `seed_db.py`
  and DFD test instructions.
- `docs/using-tank.md` — new "Threat modeling a service with DFD" workflow section.
- `docs/README.md` — phase table updated to include 2.1/2.2/2.3/3.1/3.2/3.3/3.4.
- `docs/features/README.md` — 3.4 entry added.

### Tradeoffs / known gaps

- `seed_db.py` inserts journal entries with historical dates via direct SQL
  (bypasses `upsert_for_today`). This is the only place Tank writes journal rows
  outside the store module. Acceptable for a seed script.
- DFD `.mmd` files are intentionally excluded from `load_fixtures.py`. The DFD
  tool's ingest path is the Stage 1 upload UI, not the pipeline. The seed script
  pre-populates the analysis results so the UI shortcircuits straight to Stage 3.
- NIST CSF fixture is a fragment (8 controls, not the full 106). Enough to exercise
  cross-framework gap analysis without ballooning the token cost of a full ingest.

---

## 2026-05-26 — DFD & Threat Model Revamp (3.2 rewrite)

### Goal

Replace the minimal 2-tab input form and flat threat table with a professional
three-stage pipeline: four input modes → 4-step SSE progress tracker → split-panel
interactive workspace. Elevate DFD from a quick prototype to a first-class feature
with richer threat schema, diagram interactivity, cross-panel linking, project
context awareness, and professional PDF export.

### What got built

**Schema (`app/schemas.py`)**

Renamed DFD `STRIDEThreat` → `DFDThreat` to fix naming collision with the
reports-module `STRIDEThreat`. Added new fields: `threat_id` (sequential T001…),
`element_label`, `title`, `cvss_estimate: float | None`, `references: list[str]`.
Added `DFDMermaidGeneration` schema for generate-from-doc and generate-from-description flows.

**DB migration (`app/db.py`)**

`_migrate_dfd_columns()` adds `input_format TEXT`, `project_id TEXT`, and
`cached INTEGER NOT NULL DEFAULT 0` to `dfd_analyses` via `_add_col_safe`
(idempotent). Called from `_init_schema()` on every boot.

**Storage (`app/storage/dfd_store.py`)**

`insert()` now accepts `input_format`, `project_id`, `cached`. `list_recent()`
accepts optional `project_id` filter. `_row_to_dict()` normalizes rows (parses
`analysis_json`, converts `cached` to bool).

**Prompts**

- `prompts/dfd_stride.md` — updated for new threat fields; Low severity color
  changed from `#2563eb` → `#4F46E5` (aligns with CSS vars); severity indicator
  added to annotated node labels (`⚠ H`); project context injection instruction.
- `prompts/dfd_generate_doc.md` — new: generate Mermaid DFD from an architecture
  document (PDF/DOCX/TXT/MD).
- `prompts/dfd_generate_desc.md` — new: generate Mermaid DFD from plain-language
  system description.

**Analyzer (`app/claude/dfd_analyzer.py`)**

Added `generate_from_description()`, `generate_from_document()` (uses `pypdf` /
`python-docx` for local text extraction). Updated `analyze_mermaid()` and
`analyze_image()` to accept `project_id`, `project_notes`, `input_format`; all
return `(dfd_id, analysis, from_cache)` tuples.

**Router (`app/routers/dfd.py`)**

New endpoints: `POST /api/dfd/generate-from-description`, `POST /api/dfd/generate-from-doc`,
`POST /api/dfd/start-analysis` (returns `task_id`), `POST /api/dfd/start-analysis-image`,
`GET /api/dfd/task/{task_id}/stream` (SSE). New `format=original_mmd` export.
JSON export updated with a metadata wrapper. Legacy `POST /api/dfd/analyze`
retained for backward compat.

**Stage 1 — `dfd.html` (complete rewrite)**

4-tab mode selector: Paste Mermaid / Upload File / From Document / From Description.
Tab A: debounced live preview, "Load example" 6–8 node DFD. Tab B: drag-drop zone
with per-extension behavior (images stay as images; text files populate Tab A).
Tabs C/D: generate via Claude → populate Tab A. Submit launches SSE-tracked
analysis (Stage 2 progress tracker in-page).

**Stage 3 — `dfd_detail.html` (complete rewrite)**

Split-panel workspace with drag-resize handle. Mermaid rendered with custom Nyx
theme (`theme: 'base'` + `themeVariables`). SVG click/hover interactivity via
`<g class="node">` elements. Zoom via CSS `transform: scale()`. Findings panel:
summary strip, severity + STRIDE filter pills with CSS transitions, threat cards
with collapsible mitigation and `<details>`, CVSS, ref-pills, "Highlight in
diagram →" cross-link. Print-only section for professional PDF layout
(cover + diagram + threat table + STRIDE 6×4 matrix + Mermaid appendix).

**Style (`app/static/style.css`)**

Added `--sev-critical/high/medium/low` CSS variables to `:root` as the single
source of truth for severity colors. All Stage 1 + Stage 3 UI styles. Comprehensive
`@media print` for PDF export.

### Tradeoffs

- **SSE steps bracket a single Claude call** — Steps 1 and 4 are genuinely real
  (input validation and DB storage). Steps 2–3 bracket the Claude call. The
  4-step UX communicates meaningful progress without requiring the analysis to be
  split into multiple API calls.
- **PDF via `@print` CSS only** — No jsPDF/html2canvas dependency. Produces a
  professional layout without adding a build step or large client-side library.
- **Old-schema backward compat** — Existing `dfd_analyses` rows have no `threat_id`,
  `title`, etc. Template uses Jinja2 `| default()` fallbacks so old records still
  render correctly alongside new ones.

---

## 2026-05-25 — Projects dashboard + color/notes + project-scoped chat (3.3)

### Goal

Elevate the existing project compartmentalization (schema + FK layer from Phase 16) into a
fully usable feature: card-based dashboard, color/notes fields, project detail page,
project notes in the system prompt for project-scoped chat, and data migration for any
previously unscoped rows.

### What got built

**Phase 1 — Data model**

- `app/db.py` — `_migrate_project_fields(conn)` adds `color TEXT NOT NULL DEFAULT '#6366f1'`
  and `notes TEXT NOT NULL DEFAULT ''` to the `projects` table via `_add_col_safe` (idempotent).
  `_migrate_unscoped_data(conn)` assigns any NULL `project_id` rows across 7 artifact tables
  to the Default project and emits a warning log (ran on first boot: 29 docs, 6 convs, 5
  reports). `_seed_default_project` back-fills `color` on the existing default row if it
  predates this migration.
- `app/storage/projects_store.py` — `create_project()` now accepts `color` and `notes`;
  `list_projects()` / `get_project()` return them via `SELECT *`; new `update_project(id,
  **kwargs)` enables PATCH-style edits for name, description, emoji, color, notes.

**Phase 2 — Routing**

- `app/routers/projects.py` — `GET /projects/{project_id}` detail page with scoped
  doc/conv/report counts + recent-5 lists; `PATCH /api/projects/{id}` with `UpdateProject`
  Pydantic model; `CreateProject` updated with `color` and `notes` fields.
- `app/templates/project_detail.html` — new template: 6px color accent header, emoji +
  name, notes block (omitted when empty), 3-metric grid, recent docs/convs lists, inline
  edit form with native `<input type="color">` and emoji picker, JS DOM-update on save
  (no reload).

**Phase 3 — Dashboard UI**

- `app/templates/projects.html` — rebuilt as a CSS Grid card dashboard. Each card shows
  the color accent bar, emoji icon, name, description, active badge, and "Open → / Switch
  to / Delete" actions. `tank_last_opened_project` localStorage key written on card open;
  read on page load to add `.proj-card--last-opened` class (CSS `order: -1` sorts it
  first). "New project" toggle collapses inline into a form with emoji + color pickers.
- `app/static/style.css` — `.proj-grid`, `.proj-card`, `.proj-card__accent`,
  `.proj-card__body`, `.proj-card__icon`, `.proj-card__name`, `.proj-card__desc`,
  `.proj-card__actions`, `.proj-card--last-opened`.

**Phase 5 — Auth flow**

- `app/routers/pages.py` — home route validates the stored `active_project_id` against the
  DB on every request; if the row no longer exists (e.g. project was deleted), resets to
  `"default"` and continues (self-healing, no 500).

**Phase 6 — Project-scoped chat**

- `app/claude/caching.py` — `build_system_block(role_mode, lens, project_notes="")` gains
  an optional `project_notes` param. When non-empty, appends a `## Project Context` section
  inside the cached system block. When empty (global / side-panel conversations), omitted.
- `app/claude/chat.py` — `run_turn()` checks `conv.get("project_id")`; if set, fetches the
  project and passes `project["notes"]` to `build_system_block()`. Side-panel conversations
  have no `project_id`, so they never receive project notes.

**Phase 7 — Data migration**

Already described above — runs automatically at startup, idempotent.

### Tradeoffs

- **color via `<input type="color">`**: browser-native picker, zero new JS dependencies.
  Output is always a 6-char hex string. The CSS custom property `--proj-color` on each
  card makes the accent bar a single-line style rule.
- **notes in the system prompt cache**: adding project notes to the system block breaks the
  prompt-cache hit for that project if notes change, but notes are infrequently edited. The
  cache breakpoint is still valuable for long-running project sessions where notes are stable.
- **`SELECT *` on projects**: works because `list_projects()` / `get_project()` return
  plain dicts; if columns are added in future they're automatically included. The risk
  (exposing unexpected columns) is minimal for a local single-user app.

---

## 2026-05-25 — Update batch: 2.2 / 2.3 / 2.1 / 3.1 / 3.2

### Goal

Fix a significant token cost undercount ($0.27 displayed vs ~$3.00 actual),
reduce API spend on extraction tasks, add Markdown rendering to reports,
redesign the navigation, and ship DFD threat modeling as a new feature.

### What got built

**2.2 — Token cost counter fix**

Root causes were twofold: (1) the `reports` table was missing
`cache_read_in` / `cache_create_in` columns, so cache-discounted tokens were
billed at full input price; (2) 13+ Claude modules made untracked API calls
that never entered the cost calculation at all.

- `app/db.py` — `_migrate_reports_cache_columns()` adds the two columns to
  `reports` via `_add_col_safe` (idempotent). New `api_calls` table captures
  all untracked calls: `(id, call_site, model, tokens_in, tokens_out,
  cache_read_in, cache_create_in, created_at)`.
- `app/storage/api_calls_store.py` — new store; `record()` is the writer.
- `app/storage/reports_store.py` — `insert()` now accepts and stores cache
  columns.
- `app/claude/reports.py` — `_finalize()` passes cache metrics through.
- `app/routers/pages.py` — `/api/usage/cost` now sums from all three tables
  (`messages`, `reports`, `api_calls`) across all four token fields.
- `app/config.py` — `log_token_usage(call_site, model, usage)` is the single
  function all Claude modules must call after each response. Writes to
  `api_calls`; logs to console when `TANK_DEBUG_TOKENS=1`.
- All 13 previously-untracked modules wired up: `extractor`, `decisions`,
  `notes`, `nudges`, `attack_mapping`, `iam_translator`, `meeting_prep`,
  `journal_extractor`, `lesson_extractor`, `design_review`,
  `postmortem_authoring`, `tabletop`, `threat_modeling`, `anniversary`,
  `day1_brief`, `philosophy`.

**2.3 — Claude API optimization**

- `app/claude/extractor.py` — switched from Sonnet to `HAIKU_MODEL`
  (`claude-haiku-4-5-20251001`). Removed `thinking={"type": "adaptive"}` (Haiku
  doesn't support extended thinking). Entity extraction is structured JSON with
  a known schema — well within Haiku's capability at ~10× lower cost.
- `app/claude/meeting_prep.py`, `journal_extractor.py`, `lesson_extractor.py`
  — switched to Haiku.
- `app/claude/nudges.py` — question-of-week generation switched to Haiku.
- `app/config.py` — `HAIKU_MODEL` constant promoted to `config.py`; all
  affected modules import from there.

**2.1 — Markdown rendering + report exports**

- `app/templates/base.html` — `marked.min.js` added via CDN.
- `app/templates/report_detail.html` — replaced `<pre>` with a `<div
  id="report-md-output">` populated by `marked.parse(...)` on load. Added PDF
  (via `window.print()`) and Markdown download buttons.
- `app/static/style.css` — `.markdown-body` scoped styles for headings, tables,
  code blocks, lists. `@media print` block hides sidebar/topbar/actions.

**3.1 — App redesign**

- `app/templates/base.html` — flat topbar nav replaced with `<aside
  class="sidebar">` with four groups: Workspace, Pipeline, Workstreams, System.
  Active-item highlighting via JS `location.pathname` check. Cost badge moved
  to sidebar footer.
- `app/static/style.css` — full sidebar layout (220px fixed width, responsive
  hide at <900px). Empty-state component. `.btn-ghost` class.
- `app/templates/index.html` — first-run empty state when no documents
  ingested.

**3.2 — DFD threat modeling**

New feature end-to-end. See `docs/features/dfd-analysis.md` for the user-
facing reference.

- `app/claude/dfd_analyzer.py` — `analyze_mermaid(src, force=False)` (SHA-256
  cached), `analyze_image(bytes, media_type)`, `improve_mermaid(src,
  kb_context)`. Cache bypass via `force=True`.
- `app/routers/dfd.py` — `GET /dfd`, `GET /dfd/{id}`, `POST /api/dfd/analyze`
  (with `force` form field), `POST /api/dfd/{id}/improve` (KB-aware diagram
  completion), `GET /api/dfd/{id}/export?format=mmd|json`.
- `app/storage/dfd_store.py` — `insert`, `get`, `get_by_hash`, `list_recent`.
- `app/schemas.py` — `DFDElement`, `STRIDEThreat`, `DFDAnalysis`,
  `DFDImprovement`.
- `app/main.py` — `dfd.router` registered.
- `app/templates/dfd.html` — tab bar (Mermaid / Image), textarea, file inputs,
  submit with loading state, recent analyses list, empty state.
- `app/templates/dfd_detail.html` — annotated Mermaid diagram (rendered by
  `mermaid.js` CDN), severity-sorted threat table, color legend. Re-analyze and
  Improve diagram buttons. Improve section renders result inline with suggestions
  list and "Run STRIDE on improved diagram" action.
- `prompts/dfd_stride.md` — STRIDE analysis prompt with severity rubric and
  color annotation instructions.
- `prompts/dfd_improve.md` — diagram-completion prompt; instructs Claude to
  preserve all existing nodes and only add what's missing.
- `app/templates/ingest.html` — DFD callout at page bottom.
- `CLAUDE.md` — created (previously absent).

### Tradeoffs

- **Haiku for extraction**: Haiku lacks extended thinking and is weaker on
  ambiguous entity classification. For the structured schemas Tank uses
  (known field names, constrained enums) the quality difference is negligible.
  Revert to Sonnet in `extractor.py` if entity quality degrades noticeably.
- **DFD caching**: SHA-256 means even a single character change produces a
  cache miss. This is intentional — avoids stale threat tables after diagram
  edits. Re-analyze button makes the UX friction manageable.
- **`window.print()` for PDF**: avoids `jsPDF` + `html2canvas` dependency
  (complex tables break under canvas rendering). Print CSS hides UI chrome.
  Trade-off: output is browser-dependent. Acceptable for an internal tool.

---

## 2026-05-20 — Plan + Phase 1 + Phase 2

### Goal

Stand up Tank's foundation: project skeleton, SQLite schema, redaction
engine. Headline guarantee from day one: nothing leaves the machine in
cleartext.

### What got built

- **Plan file** at `~/.claude/plans/imagine-you-are-a-fizzy-crystal.md`.
  Full architecture: 17 SQLite tables, redaction layer design, ingest
  pipeline, Claude chat with SSE + tool use, six reports, partner mode.
  Approved by the user with edits (renamed `recon-companion` → `Tank`,
  removed Opus tier, mandated single Sonnet model).
- **Project skeleton** at `/Users/manuel.del.rio/projects/tank/`:
  `app/{main,config,db,schemas,role}.py`, `app/redact/{engine,rules,secrets,store,config}.py`,
  `app/routers/{pages,onboarding}.py`, `app/templates/{base,index,onboarding}.html`,
  `app/static/style.css`, `scripts/{start.sh,stop.sh}`,
  `tests/{conftest,test_redaction}.py`, README, requirements.txt,
  .env.example, .gitignore.
- **17 SQLite tables** initialized on boot: documents, chunks,
  chunks_fts, entities, entity_chunks, relationships, redaction_map,
  redaction_rules, conversations, messages, reports, nudges, notes,
  app_state.
- **Redaction engine** with 11 categories: email, internal_hostname
  (custom TLD + defaults), public_hostname (off), ipv4_private
  (RFC1918 + loopback + link-local + CGNAT), ipv4_public (off),
  aws_account_id (context-gated), aws_arn, gcp_project (context-gated),
  azure_subscription, secret_token (curated detect-secrets plugins +
  entropy fallback, non-disableable, one-way SHA-256 hashed),
  person_name (off, requires spaCy). Custom-regex rules via
  `redaction_rules` table.
- **28/28 redaction tests passing.** Determinism (same input ↔ same
  placeholder across calls), dedup, overlap resolution, rehydration
  longest-first, secret one-way hashing, custom rules.

### Key design decisions

- **Pre-redact at ingest time**, not at send time. Costs ~10ms/chunk
  but eliminates "we forgot to redact in this code path" bugs forever.
- **Secrets are one-way.** `redaction_map.original_text` for
  `secret_token` is the SHA-256 hash, never cleartext. Rehydrating
  secrets is impossible by design — user must look up the source doc.
- **Sonnet-only.** Single `MODEL = "claude-sonnet-4-6"` constant. No
  Opus tier in v1. Uniform prompt-cache behavior, simpler config.
- **Single SQLite connection + threading.Lock.** Explicit single-user
  assumption; matches the job-fit reference pattern.
- **Provenance on every entity.** `source` / `inferred` / `claim` /
  `user`. Drives the trust badges in the UI; queryable, not cosmetic.

### Files added (alphabetical)

```
tank/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── main.py
│   ├── redact/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── engine.py
│   │   ├── rules.py
│   │   ├── secrets.py
│   │   └── store.py
│   ├── role.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── onboarding.py
│   │   └── pages.py
│   ├── schemas.py
│   ├── static/style.css
│   └── templates/{base,index,onboarding}.html
├── scripts/
│   ├── start.sh
│   └── stop.sh
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_redaction.py
```

### Tradeoffs taken

- Person-name redaction off by default — readability vs privacy.
- No remote embedding API (Phase 3+) — privacy beats retrieval quality.
- sqlite-vec for vectors instead of a real vector DB — operational
  simplicity, plenty fast at this scale.

### Known gaps at this point

- No ingestion yet — DB tables exist but nothing fills them.
- macOS system Python 3.9 can't load sqlite-vec (`enable_load_extension`
  missing). FTS5 still works for keyword search. Resolved by upgrading
  Python to 3.11+ via Homebrew when convenient.
- spaCy excluded from requirements.txt (needs Python 3.10+); person-name
  redaction off as a result.

### How to verify

```bash
cd tank && source .venv/bin/activate
python -m pytest -q            # → 28/28 pass
./scripts/start.sh             # → http://localhost:8000 renders onboarding
```

---

## 2026-05-20 — Phase 2.5: Helix Robotics fixture pack

### Goal

A complete, internally-consistent fictional company so the rest of the
build (ingestion, chat, reports) has realistic-looking inputs from day
one. The user wants something to "play around with."

### What got built

A `tank/sample_data/` corpus: 23 hand-crafted files + 2 small repos
simulating **Helix Robotics** — a fictional B2B SaaS doing payments +
identity for robotics OEMs. ~80 employees, Series B, AWS-heavy.
(Later expanded to 26 files + 3 new subfolders to cover all parser types.)

- **sample_data/README.md** — scenario + how-to-load
- **sample_data/company.md** — 1-page company overview
- **sample_data/architecture/** (4 files + generated PDF + PNG)
- **sample_data/repos/payments-api/** (12 files, Python FastAPI; CODEOWNERS
  *deliberately* contradicts CMDB to trigger contradiction-surfacing
  nudge later)
- **sample_data/repos/webhook-router/** (8 files, Go; no postmortem, no
  runbook — planted gap)
- **sample_data/cmdb/** (services.csv with 8 services, cloud-accounts.csv
  with 5 AWS accounts)
- **sample_data/people/** (org-chart, on-call.csv, 1-1-cadence.md)
- **sample_data/policies/** (access-policy + generated DOCX,
  incident-response, data-classification)
- **sample_data/runbooks/** (service-restart, rotate-customer-api-key,
  investigate-suspicious-login)
- **sample_data/postmortems/** (Vault sidecar outage; AWS-key leak close
  call)
- **sample_data/seeds/** (leaked-key-example.md and internal-host-list.md
  for redaction testing)
- **scripts/_gen_fixtures.py** — synthesizes PDF/DOCX/PNG from MD
- **scripts/load_fixtures.py** — bulk loader

### Planted edge cases

Each maps to a Tank feature to exercise later:

| Planted | Tests |
| --- | --- |
| `AKIAIOSFODNN7EXAMPLE` + matching secret | secret_token + one-way hash |
| `xoxb-...` Slack token + `ghp_...` GitHub PAT | detect-secrets plugins |
| `999988887777` near "AWS account" | aws_account_id rule |
| `payments.helix.internal` in 4+ docs | placeholder reuse |
| CODEOWNERS says Marcus, CMDB says Sam | contradiction nudge |
| webhook-router has no postmortem/runbook | cross-service gap report |
| Diana mentioned 3× but no entity card | pattern_detection nudge |
| Mixed criticality (CMDB "critical" vs runbook "tier-2") | contradiction |

### Verification

```bash
python -m scripts._gen_fixtures   # PDF + PNG + DOCX generated
python -m scripts.load_fixtures --dry-run
# → 26 files + 2 repos planned across 4 categories
```

Redaction sanity-check on `seeds/leaked-key-example.md`:
**7/7 secrets caught, all stored as 64-char SHA-256 hashes.**
Redaction sanity-check on `seeds/internal-host-list.md`:
**13/13 internal hostnames + 8/8 private IPs caught; 0 public** (correct).

### Tradeoffs

- Sample data is version-controlled (in `tank/sample_data/`), not gitignored.
  Acceptable because all content is synthetic — no real customer data.
- The DOCX/PDF/PNG are *generated* artifacts; the markdown sources are
  the source of truth. `_gen_fixtures.py` produces them deterministically.
- The two repos contain plausible-looking Go and Python skeletons but
  aren't runnable — code-fact extraction in Phase 5 only needs the
  manifest/Dockerfile/README shape.

### Files added

~30 sample files + 2 scripts. Net: `tank/sample_data/` (23 MD/CSV + 3
generated binaries + 2 repos, later expanded to 26 files) and
`tank/scripts/{_gen_fixtures,load_fixtures}.py`.

---

## 2026-05-20 — Phases 3-11 (full build push)

### Goal

Ship the rest of Tank in a single push: ingestion pipeline, KB layer,
remaining parsers, chat with SSE + tool use, six reports, partner-mode
daily companion features, UI polish, privacy verification, and opt-in
continuous-ingestion connectors. The user explicitly asked for "all
the phases now" with a recap markdown they can review later.

### What got built (by phase)

#### Phase 3 — Ingestion pipeline foundation

- **Storage stores** for documents, chunks (with FTS5 + sqlite-vec
  writes), entities (with `(type, name_normalized)` dedup), and
  relationships (with `(src, dst, kind)` dedup). All take `LOCK` for
  writes.
- **Pipeline** (`app/ingest/pipeline.py`): `parse → chunk → redact →
  embed → store → extract`. Two entrypoints — `ingest(path, category)`
  for single files and `ingest_repo(root)` for source repos.
- **Chunker**: `RecursiveCharacterTextSplitter` + `tiktoken`,
  target 800 tokens with 120-token overlap, snaps to paragraph
  boundaries.
- **Embedder**: lazy singleton wrapping
  `sentence-transformers/all-MiniLM-L6-v2`. Embeds the redacted
  chunk only.
- **Markdown + PDF parsers** with section-path preservation.
- **Entity extractor** (`app/claude/extractor.py`): batches 4 chunks
  per call to Sonnet 4.6 with `messages.parse(output_format=ChunkExtraction)`.
- **Prompt** `prompts/extract_entities.md` — typed schema, hard rules
  ("never invent", "no placeholder unpacking"), citation discipline.
- **Routers**: `POST /api/ingest/file`, `/path`, `/repo`; `GET /api/documents`.
- **CLI**: `scripts/ingest_cli.py` for one-off ingestion from the shell.

#### Phase 4 — KB layer

- **Hybrid retrieval** (`app/kb/search.py`): vector ANN via sqlite-vec
  + BM25 via FTS5 + reciprocal rank fusion. Falls back to FTS-only if
  sqlite-vec didn't load.
- **Entity card builder** (`app/kb/entities.py`): full entity + up to
  5 linked chunks + edges count.
- **Relationship traversal** (`app/kb/relationships.py`): N-hop graph
  walks, plus a `graph_for_type` slice used by the entity-graph viz.
- **Anthropic tool schemas** (`app/kb/tools.py`): 6 tools exposed to
  the chat assistant — `search_kb`, `get_entity`, `list_relationships`,
  `find_control_gaps`, `list_entities`, `get_document`. Each maps to
  a local executor; tool results are pre-redacted, with a defense-in-
  depth redaction pass in chat.

#### Phase 5 — Remaining parsers

- **DOCX parser**: walks paragraphs, builds section_path from heading
  styles, flattens tables to TSV.
- **CSV/JSON parser**: row-grouping (25 rows/chunk) for CMDB-shaped
  data; column-mapping side-channel via `.column-map.json`.
- **Image parser** (`app/ingest/parsers/image.py`): base64-encodes the
  bytes, calls Sonnet 4.6 vision with `extract_arch_diagram.md`. The
  parser stashes the structured extraction in `meta["vision"]`; the
  extractor module picks it up and persists entities/edges.
- **Repo walker** (`app/ingest/parsers/repo.py` + `code_facts.py`):
  walks the repo (`.gitignore`-aware), collects language LOC, manifest
  contents, Dockerfile facts, CI files, auth/secrets grep hits,
  CODEOWNERS, README, ARCHITECTURE.md. Renders to a summary doc;
  **no raw source code is sent to Claude**.
- **Prompts**: `extract_arch_diagram.md`, `extract_repo_summary.md`.

#### Phase 6 — Chat with SSE + tool use

The biggest unlock. Pioneers both streaming and tool use in your stack
(neither pattern existed in job-fit / resume-analyzer).

- **Conversations + messages stores**.
- **Caching helper** (`app/claude/caching.py`): builds two cache-
  controlled blocks per request — system + KB context.
- **Streaming chat loop** (`app/claude/chat.py`):
  - Redacts user msg → embeds → hybrid retrieval → entity cards.
  - Builds messages with cached system + cached KB block.
  - `client.messages.stream(...)` with tools.
  - Loop iterates: text deltas via SSE, tool_use → execute → tool_result
    → continue until `end_turn`.
  - Rehydrates response, persists redacted_view + display_view +
    citations + token usage.
- **In-process event bus** (`app/claude/event_bus.py`): topic-keyed
  asyncio queues for SSE consumers.
- **Router** (`app/routers/chat.py`): `POST /api/conversations`,
  `POST .../messages`, `GET .../stream` (SSE via sse-starlette).
- **Chat UI** (`templates/chat.html`): conversation list + streaming
  bubble with tool-use trace + "show reasoning" disclosure.
- **System prompts**:
  - `chat_system_ic.md` — Staff/Senior IC lens, technical depth.
  - `chat_system_manager.md` — Manager lens, org context.
  - `chat_system_both.md` — dual-lens default.
  - `chat_lens_{map,prioritize,execute,maintain}.md` — tenure framing.

#### Phase 7 — Reports

Six generators sharing a cached scope block, so a 6-report run is
~2× cheaper than running each cold.

- **Pydantic schemas** in `app/schemas.py` for all six output shapes
  (ThreatLandscapeReport, CrossServiceGapsReport, PlanReport,
  StakeholderMap, QuestionList, ControlMatrix).
- **Generators** (`app/claude/reports.py`): one function per kind,
  all routing through `_run(prompt, OutputType, scope)`. Each renders
  to Markdown and persists both redacted (audit) + rehydrated (display).
- **Prompts**: `report_threat_landscape.md`, `report_cross_service_gaps.md`,
  `report_30_60_90.md`, `report_stakeholder_map.md`,
  `report_questions_for_team.md`, `report_control_matrix.md`.
- **Router + templates**: `/reports` library page + `/reports/{id}`
  detail page with audit toggle.
- **Markdown export**: `GET /api/reports/{id}/export?format=md`.

#### Phase 8 — Partner mode (daily-companion machinery)

The phase that turns Tank from a recon tool into a daily companion.

- **Daily-use schema additions**:
  - `journal_entries`, `followups`, `report_subscriptions`,
    `usage_events`, `watchers`, `meetings` tables.
  - `app_state.tenure_started_at` + `last_journal_at` columns
    (additive migration via `_migrate_app_state_columns`).
- **Tenure-aware lens** (`app/role.py::current_lens()`): returns
  `map` (days 1-14), `prioritize` (15-60), `execute` (61-180),
  `maintain` (180+). Chat system prompts and the home dashboard
  adapt automatically.
- **Stores**: `journal_store`, `followups_store`, `subscriptions_store`,
  `usage_store`, `nudges_store`, `notes_store`.
- **Claude-side generators**:
  - `nudges.py` — 8 nudge kinds: coverage_gap, stale_context,
    pattern_detection, contradiction, abandoned_thread,
    question_of_week (LLM), journal_followup_suggestion,
    + the new dependency_cve (Phase 11). Rate-limited to 2/day.
  - `meeting_prep.py` — one-screen brief: who they are, world,
    overlap, unknowns, ranked questions, one thing to offer.
  - `notes.py` — diff extraction from freewrite, user-confirmed
    commit to KB with `provenance='user'`.
  - `day1_brief.py` — runs at end of onboarding. Scope echo, top 5
    entities, week-1 questions, week-1 reading, week-1 meetings.
    Persisted as a Report (`kind='day1_brief'`).
  - `anniversary.py` — Day 30/60/90/180/365 retros. Persisted as
    `kind='anniversary_<N>'`.
  - `journal_extractor.py` — light-touch parse of evening journal
    entries.
- **Prompts**: `meeting_prep.md`, `notes_to_kb.md`, `nudge_generator.md`,
  `day1_brief.md`, `anniversary.md`, `journal_extractor.md`.
- **Background scheduler** (`app/claude/scheduler.py`):
  Single asyncio.Task, started in lifespan, cancelled on shutdown.
  Wakes every 60s; fires:
  - Daily digest at `app_state.digest_time` → nudge regen,
    subscription dispatch, anniversary check.
  - Configured reflection day 16:00 → weekly reflection trigger.
  - Weekday evening 18:00 → journal prompt nudge if no entry today.
- **Conversational onboarding rewrite** (`onboarding.html` +
  `onboarding.py` router): 5-step flow that sets `tenure_started_at`
  and kicks off Day-1 brief generation as a background task.
- **Routers**: nudges, meeting_prep, notes, journal, followups,
  subscriptions.
- **Templates**: onboarding (rewritten), meeting_prep, notes,
  index (rewritten with today-grid: digest + follow-ups + hot
  entities + quick actions).

#### Phase 9 — UI polish

- **Entity browser** (`templates/entities.html` + `entity_detail.html`):
  tabbed-by-type list, full card with attributes, linked chunks,
  edges, and entity-specific actions (generate threat report for
  Services, prep meeting for People).
- **Entity graph viz** (`static/graph.js`): canvas-based
  force-directed layout. No external graph library — keeps the
  project dependency-lean. Click to drill into an entity.
- **Settings page** (`templates/settings.html`): role-mode picker,
  cadence (digest time + reflection day), redaction rule toggles
  with per-category match counts, wipe-all button.
- **Router** (`routers/settings.py`): redaction toggles, role/cadence
  updates, `POST /api/wipe` (one-button nuke).

#### Phase 10 — Privacy verification

- **`scripts/verify_privacy.py`**: scans the SQLite DB for any
  fixture identifier (planted secrets, internal hostnames, fake
  AWS account IDs, employee emails) appearing in any column that
  gets sent to Claude (`chunks.text_redacted`,
  `messages.redacted_view`, `reports.content_md_redacted`,
  `journal_entries.body_redacted`, etc.). Exit code 1 on any hit.
- **Helix fixture-pack mode**: `--fixture-pack` flag enables
  pre-baked Helix Robotics needles
  (AKIAIOSFODNN7EXAMPLE, 999988887777, helixrobotics.com, etc).

#### Phase 11 — Opt-in continuous-ingestion connectors

All disabled by default. Enabled via `Settings → Integrations`.

- **Folder watcher**: polls a local directory for new/changed files,
  auto-ingests via the existing pipeline.
- **ICS calendar watcher**: fetches a public/CalDAV `.ics` URL,
  populates the `meetings` table.
- **CVE feed watcher**: NVD subscription filtered by deps Tank
  knows about. Surfaces `dependency_cve` nudges.
- **GitHub poller**: opt-in token (`TANK_GITHUB_TOKEN`); polls
  configured repos for sensitive-path PRs.
- **Integrations router** (`/api/integrations/watchers/*`): CRUD +
  scan-now.

### Verification results

```
pytest                                  → 28/28 pass
boot smoke test (TestClient end-to-end):
  GET /                                 → 302 /onboarding ✓
  GET /onboarding                       → 200 (5043 bytes) ✓
  5-step onboarding flow                → all ✓
  GET / (post-onboard, tenure set)      → 200 with "Map mode" lens ✓
  GET /chat                             → 200 ✓
  GET /reports                          → 200 ✓
  GET /meeting-prep                     → 200 ✓
  GET /notes                            → 200 ✓
  GET /entities                         → 200 ✓
  GET /settings                         → 200 ✓
  GET /api/nudges/today                 → 200 ✓
  GET /api/followups                    → 200 ✓
  GET /api/journal/today                → 200 ✓
  GET /api/subscriptions                → 200 ✓
  GET /api/integrations/watchers        → 200 ✓
```

**66 routes total.** Day-1 brief generation logs an expected
exception during the smoke test (no `ANTHROPIC_API_KEY` is set in
the test env); it runs as a background task and doesn't block
onboarding completion.

### Tradeoffs accepted

1. **Smoke tests, not full E2E with the live API.** Hitting the
   Anthropic API during the test session would cost real money and
   require a key; we verified everything imports cleanly and routes
   200 instead. Real verification against the API needs Phase 10's
   mitmproxy capture run with a real key.
2. **CVE + GitHub watchers ship as scaffolds**: the data model and
   the contract are in place; the full implementations require an
   NVD API key + a GitHub PAT respectively, both gated behind env
   vars.
3. **Graph viz is pure canvas** instead of pulling in `vis-network`
   or `cytoscape.js`. Keeps the dep tree minimal at the cost of
   slightly cruder visuals. Easy to swap later.
4. **Anthropic SDK streaming bridges to asyncio via run_in_executor**
   in chat.py rather than a fully native async iterator. The SDK's
   sync streaming context manager is simpler to reason about and
   our per-conversation queues already provide the asyncio boundary
   for SSE.
5. **No persistent task queue** — partner-mode work runs in
   FastAPI's `BackgroundTasks` or asyncio.create_task. Single-user,
   single-process; durable queueing would be over-engineering.

### Known gaps at this point

- **First chat turn against real Claude API hasn't been live-tested**
  in this session (no API key in the smoke env). The shape is
  correct against Anthropic SDK 0.92+, but expect minor adjustments
  on first real call.
- **sqlite-vec is still disabled** on this dev machine's Python 3.9.
  Hybrid retrieval gracefully falls back to FTS-only. To get vector
  search, switch to Python 3.11+ from Homebrew or python.org.
- **Person-name redaction still off** by default (spaCy needs
  Python 3.10+).
- **CSV column-mapping UI** isn't built yet; the parser reads
  `.column-map.json` if present, otherwise just chunks rows
  generically. Phase-9 follow-up.
- **PDF→DOCX export** of reports not implemented. Markdown export
  ships; PDF needs weasyprint (not installed by default).
- **No live live-reload of nudges in the UI** — the home dashboard
  re-renders on action, not via SSE push. The event bus is ready for
  this but the UI side hasn't subscribed.

### How to verify everything still works

```bash
cd tank && source .venv/bin/activate
python -m pytest -q                       # → 28/28
./scripts/start.sh                        # → http://localhost:8000

# Once the server is up, try:
python -m scripts.load_fixtures --dry-run # → 26 files + 2 repos planned
python -m scripts.load_fixtures           # → actual ingest (uses your API key)

# After ingest:
sqlite3 ~/.tank/db.sqlite \
  "SELECT category, COUNT(*) FROM redaction_map GROUP BY category;"

# Privacy assertion:
python -m scripts.verify_privacy --fixture-pack
```

### Files added in this session (alphabetical, abbreviated)

```
app/claude/{anniversary,caching,chat,day1_brief,event_bus,extractor,
            journal_extractor,meeting_prep,notes,nudges,reports,scheduler}.py
app/ingest/{__init__,chunker,code_facts,embedder,pipeline}.py
app/ingest/parsers/{__init__,_base,csv_json,docx,image,markdown,pdf}.py
app/ingest/watchers/{__init__,cve,folder,github,ics}.py
app/kb/{__init__,entities,relationships,search,tools}.py
app/routers/{chat,entities,followups,ingest,integrations,journal,
             meeting_prep,notes,nudges,reports,settings,subscriptions}.py
app/storage/{chunks,conversations,documents,entities,followups,journal,
             messages,notes,nudges,relationships,reports,subscriptions,
             usage}_store.py
app/static/graph.js
app/templates/{chat,entities,entity_detail,meeting_prep,notes,
               onboarding,report_detail,reports,settings}.html
prompts/{anniversary,chat_lens_execute,chat_lens_maintain,chat_lens_map,
         chat_lens_prioritize,chat_system_both,chat_system_ic,
         chat_system_manager,day1_brief,extract_arch_diagram,
         extract_entities,extract_repo_summary,journal_extractor,
         meeting_prep,notes_to_kb,nudge_generator,
         report_30_60_90,report_control_matrix,report_cross_service_gaps,
         report_questions_for_team,report_stakeholder_map,
         report_threat_landscape}.md
scripts/{ingest_cli,verify_privacy}.py
```

That's ~70 new files. The full project tree now sits at ~120 files
across all phases. Net: Tank is feature-complete against the original
plan.

---

## Recap — the build at-a-glance

| Phase | What it delivers | Status |
| --- | --- | --- |
| 1 | Skeleton, DB, config, start.sh, README | ✅ shipped |
| 2 | Redaction engine + 28/28 tests | ✅ shipped |
| 2.5 | Helix Robotics fixture pack (23 files, 2 repos) | ✅ shipped |
| 3 | Ingestion pipeline + storage + entity extractor | ✅ shipped |
| 4 | KB layer (search, entity cards, tool schemas) | ✅ shipped |
| 5 | Remaining parsers (DOCX, vision, CSV, repo) | ✅ shipped |
| 6 | Chat with SSE streaming + tool use | ✅ shipped |
| 7 | Six report generators sharing prompt cache | ✅ shipped |
| 8 | Partner mode + daily-companion machinery | ✅ shipped |
| 9 | UI polish (entity graph, settings, badges) | ✅ shipped |
| 10 | Privacy assertion script | ✅ shipped |
| 11 | Opt-in connectors (folder, ics, cve, github) | ✅ shipped |

## What to do next (suggested order)

1. **Get a real ANTHROPIC_API_KEY** in `.env` and run
   `./scripts/start.sh`. Complete onboarding through the UI.
2. **Ingest the Helix Robotics sample data** via `python -m scripts.load_fixtures`.
   Expect ~$5-10 in API cost for the full pack.
3. **Open `/chat`** and ask: *"What's the most security-relevant
   service in this codebase and why?"*
4. **Generate reports** from `/reports`. Start with `cross_service_gaps`
   — it'll find webhook-router's missing postmortem.
5. **Run the privacy assertion**:
   `python -m scripts.verify_privacy --fixture-pack`
   to confirm no fixture identifiers leaked into any redacted field.
6. **Upgrade to Python 3.11+** when convenient (Homebrew or python.org)
   to enable sqlite-vec for true vector search.

---

## 2026-05-20 — Phases 12-15 (true SE assistant push)

### Goal

Push Tank from "onboarding tool" into "true Security Engineer
assistant" territory. The user's framing: Tank shouldn't just help
during onboarding — it should host the artifacts a Sr/Staff/Mgr SE
writes weekly (threat models, design reviews, postmortems, tabletops,
decisions logs, lessons learned) and reason about coverage
(detections, IAM, compliance, attack surface). Generalist + AppSec
lean; strict local-only — no new outbound integrations beyond Phase 11.

### What got built (by phase)

#### Phase 12 — Living threat models + decisions log

Move from one-shot threat reports to **versioned, drift-aware** TMs
tied to architecture, plus a decisions / accepted-risk log.

- **Schema**: `threat_models` (versioned per service, frozen STRIDE
  threats, `arch_snapshot_hash` for drift detection), `decisions`
  (kind ∈ design_choice/accepted_risk/deferred_fix/security_invariant;
  status; expires_at; source; scope_entity_ids).
- **Pydantic**: `ThreatV2` (with `state` field — new/still_valid/
  invalidated/updated), `ThreatModelV2`, `ExtractedDecision`,
  `DecisionExtraction`.
- **Claude helpers**: `threat_modeling.generate(service_id)` (regen-
  aware — passes prior TM, asks Sonnet to delta), `find_drift()`,
  `decisions.extract_from_doc(doc_id)` + `commit_extraction()`.
- **Prompts**: `threat_model_v2.md`, `extract_decisions.md`.
- **Routers**: `/threat-models`, `/threat-models/{id}`, `/decisions`
  with full API surface (generate, confirm, list, version diff,
  expiring-soon, reaffirm, extract-from-doc).
- **Templates**: `threat_models.html`, `threat_model_detail.html`,
  `decisions.html`.
- **New chat tools**: `get_threat_model`, `find_decisions`,
  `get_recent_decisions`.
- **New nudges**: `architecture_drift`, `decision_expiring`,
  `unaddressed_threat`.

#### Phase 13 — Security workstreams

Tank starts hosting weekly SE work instead of just reading it.

- **Schema**: `design_reviews`, `postmortems_drafts`, `tabletops`.
- **Pydantic**: `DesignReviewChecklistItem`, `DesignReviewIntakePayload`,
  `PostmortemFields`, `PostmortemDraftPayload`, `TabletopInject`,
  `TabletopScenario`, `OnCallHandoff`, `WeeklySecurityDigest`.
- **Mini-apps** (each: store + Claude helper + router + 1-2 templates):
  - **Design reviews** (`/design-reviews`): freewrite intake → Sonnet
    seeds title/scope/risk areas/missing info/checklist → user
    works through checklist → on approve, spawn decisions tagged
    `source='design_review'`.
  - **Postmortems** (`/postmortems`): freewrite → Sonnet drafts
    structured fields → user edits → publish creates followups for
    each action item + extracts lessons (Phase-15 hook).
  - **Tabletops** (`/tabletops`): pick service+threat → Sonnet
    generates scenario + 4-6 timed injects + facilitation notes +
    rubric → capture lessons into lessons DB.
- **New report kinds**: `oncall_handoff` (per-service handoff brief),
  `weekly_security_digest` (Monday-AM cross-cutting summary).
- **Prompts**: `design_review_intake.md`,
  `design_review_checklist.md`, `postmortem_draft.md`,
  `tabletop_generator.md`, `report_oncall_handoff.md`,
  `report_weekly_security_digest.md`.
- **Scheduler hook**: nightly 22:00 tick auto-generates `meeting_prep`
  briefs for tomorrow's calendar (rate-limited to 5/day) so the
  Today widget shows "Today's briefs" instead of requiring on-demand
  requests. New `meetings_store` ships with `list_between(start, end)`.

#### Phase 14 — Coverage + visibility

Add detection rules, IAM policies, and control frameworks as ingest
types. Synthesize coverage maps over them — still strictly local.

- **EntityType extended**: `Detection`, `AttackTechnique`,
  `IAMPolicy`, `Asset`.
- **New parsers**: `sigma.py` (Sigma YAML rules), `iam.py` (AWS
  IAM JSON + K8s RBAC + GCP IAM — computes parsed risk_score
  pre-Sonnet), `control_framework.py` (CIS / NIST / SOC2 JSON).
  `parsers/__init__.py::dispatch()` now content-sniffs JSON/YAML to
  route between IAM, control_framework, Sigma, and CSV/JSON.
- **New schema**: `attack_surface_snapshots`, `compliance_evidence`.
- **KB helpers**: `kb/detections.py::find_for_technique(attack_id)`,
  `kb/iam.py::find_risks()`, `kb/compliance.py::find_evidence(control_id)`.
- **Claude analyses**:
  - `iam_translator.explain(policy_id)` — plain-English IAM walk-
    through with risk callouts. `iam_audit()` — ranks all
    IAMPolicy entities.
  - `compliance.collect_for_framework()` — iterates every Control
    entity, hybrid-searches for evidence, persists to
    `compliance_evidence`, returns the gap report.
  - `attack_mapping.generate()` — per-TM, Sonnet maps each threat to
    a MITRE technique; output cross-references KB detections to
    surface tactic-level gaps.
  - `attack_surface.snapshot()` + `history()` — weekly Endpoint
    snapshot with diff vs prior.
- **New report kinds**: `attack_mapping`, `iam_audit`.
- **New chat tools**: `find_detection_for_technique`, `find_iam_risks`,
  `find_evidence_for_control`.
- **Routers**: `/detections`, `/compliance`, `/attack-surface`,
  `/api/iam/{explain,risks}`.
- **Templates**: `detections.html`, `compliance.html`,
  `attack_surface.html`.
- **Prompts**: `iam_translator.md`, `report_attack_mapping.md`,
  `report_iam_audit.md`, `compliance_evidence_search.md`.

#### Phase 15 — Continuous learning + memory

Second-brain layer. Long-running memory that grows with tenure.

- **Schema**: `lessons`, `glossary`, `owned_entities`.
  `app_state.philosophy_doc_id` added via migration.
- **Stores**: `lessons_store` (tag-indexed + LIKE-search),
  `glossary_store` (pending vs confirmed),
  `owned_store` (single-user; role: owner/reviewer/consulted/informed).
- **Claude helpers**:
  - `lesson_extractor.extract_from_postmortem()` and
    `extract_from_design_review()` — auto-runs on publish/reject.
  - `glossary_extractor.discover()` — proposes company-specific
    jargon from a sample of recent KB chunks for user confirmation.
  - `philosophy.seed()` (Day 30) + `evolve()` (Day 60/90/180/365) —
    curated security-philosophy document; persists as a special
    Report (kind='philosophy'), pointer in `app_state`.
  - `anniversary_security.generate(day_n)` — security-focused retro
    fired alongside the existing generic anniversary retro.
- **Routers**: `/lessons` (search + tag filter), `/glossary`
  (discover + confirm/reject), `/me` (ownership dashboard with
  per-entity risk score), `/philosophy`.
- **Templates**: `lessons.html`, `glossary.html`, `me.html`,
  `philosophy.html`.
- **New chat tool**: `search_lessons(query, tag?)`.
- **Prompts**: `lesson_extractor.md`, `glossary_extract.md`,
  `philosophy_seed.md`, `philosophy_evolve.md`,
  `anniversary_security.md`.
- **Entity detail page**: added "I own this" action for Service
  entities (claims via `/api/me/owned`), "Generate threat model
  (v2)" for Services, "Explain this IAM policy" for IAMPolicy.

### Cross-cutting wiring

- **Navigation**: top bar now includes Threats, Reviews, PMs,
  Compliance, Me alongside the existing items.
- **Scheduler additions** (`scheduler.py`):
  - Nightly 22:00: auto pre-meeting briefs.
  - Sunday 09:00: weekly attack-surface snapshot.
  - Anniversary check (existing): now also fires the security retro
    + seeds/evolves the philosophy doc at the right milestones.
- **REPORT_REGISTRY**: 6 → 10 (added `oncall_handoff`,
  `weekly_security_digest`, `attack_mapping`, `iam_audit`).
- **Chat tools**: 6 → 13.
- **Nudge generators**: 7 → 10.
- **Routes**: 66 → 150.

### Privacy contract preserved

Every new ingest type (Sigma YAML, IAM JSON, framework JSON) flows
through the existing pipeline → `apply_redactions` → chunks. The
defense-in-depth `apply_redactions` pass in `chat.py` still wraps
every tool result. New chat tools (`get_threat_model`,
`find_decisions`, etc.) return pre-redacted text from local stores.
The one new "soft" category — glossary terms — is company jargon,
not PII, and surfaces only over already-redacted display text.

### Verification

```
pytest                              → 28/28 pass
app load                            → 150 routes registered
end-to-end smoke (32 routes hit):
  /threat-models                     → 200
  /decisions                         → 200
  /design-reviews + /new             → 200
  /postmortems + /new                → 200
  /tabletops + /new                  → 200
  /detections                        → 200
  /compliance                        → 200
  /attack-surface                    → 200
  /lessons                           → 200
  /glossary                          → 200
  /me                                → 200
  /philosophy                        → 200
  + 20 API endpoints                 → 200
```

### Tradeoffs accepted

1. **Phase-14 ATT&CK technique tagging via Sonnet may be noisy.**
   Mitigation: each row carries an exposure rating; UI displays
   `detections` field as the disambiguator.
2. **Compliance evidence collection is hybrid-search-driven.** A
   chunk's appearance is treated as evidence for a control if the
   embed similarity is high. This is conservative — Phase 14 ships
   `controls_with_no_evidence` gap surfacing as the safety net.
3. **Lesson extraction runs synchronously on postmortem publish.**
   For published-from-CLI cases the latency is acceptable; in the
   UI it adds ~5-10s to the publish click. Not pulled out into the
   scheduler yet.
4. **Personal ownership risk score is a heuristic.** Mixes TM drift,
   unaddressed high/high threats, expired decisions, and open
   postmortem followups into a 0-10 score. Not a CVSS replacement;
   the UI presents it as a coarse indicator.
5. **No markdown editor lib.** The postmortem editor uses raw
   textareas — readable but no preview. EasyMDE (~30kb) is the
   easy upgrade if we want it.
6. **Sigma parser depends on PyYAML** (already in requirements via
   docx → no new dep). Graceful degrade if YAML is unavailable —
   the raw file is still chunked.
7. **No live attack-surface diff alerting** — the snapshot is
   compared against prior at view time. Adding a delta nudge would
   double-count with `architecture_drift`; skipped for now.

### Known gaps at this point

- **No live API verification.** The new Sonnet call sites compile
  cleanly and import correctly, but haven't been hit against the
  real API in this session. Expect minor adjustments on first real
  call (same as Phases 6/7/8 — has happened before, fast to fix).
- **No new tests yet.** The 28/28 redaction tests still pass; new
  modules don't have unit tests. The smoke test against 32 routes
  is the main verification today. Adding per-module tests is a
  natural Phase-16 follow-up.
- **CSS for new pages is unstyled** beyond what the existing
  `style.css` provides. Tables, alerts, badges all use existing
  classes; the new pages render but don't have polish.

### Files added in this session (alphabetical, abbreviated)

```
app/claude/{anniversary_security,attack_mapping,attack_surface,
            compliance,decisions,design_review,glossary_extractor,
            iam_translator,lesson_extractor,philosophy,
            postmortem_authoring,tabletop,threat_modeling}.py
app/ingest/parsers/{control_framework,iam,sigma}.py
app/kb/{compliance,detections,iam}.py
app/routers/{attack_surface,compliance,decisions,design_reviews,
             detections,glossary,iam,lessons,me,philosophy,
             postmortems,tabletops,threat_models}.py
app/storage/{decisions,design_reviews,glossary,lessons,
             meetings,owned,postmortems,tabletops,threat_models}_store.py
app/templates/{attack_surface,compliance,decisions,design_reviews,
               design_review_detail,design_review_new,detections,
               glossary,lessons,me,philosophy,postmortems,
               postmortem_editor,postmortem_new,tabletops,
               tabletop_detail,tabletop_new,threat_models,
               threat_model_detail}.html
prompts/{anniversary_security,compliance_evidence_search,
         design_review_intake,extract_decisions,glossary_extract,
         iam_translator,lesson_extractor,philosophy_evolve,
         philosophy_seed,postmortem_draft,report_attack_mapping,
         report_iam_audit,report_oncall_handoff,
         report_weekly_security_digest,tabletop_generator,
         threat_model_v2}.md
```

Net: ~55 new files across the four phases. Schema gained 10 new
tables (`threat_models`, `decisions`, `design_reviews`,
`postmortems_drafts`, `tabletops`, `attack_surface_snapshots`,
`compliance_evidence`, `lessons`, `glossary`, `owned_entities`) +
1 column on `app_state` (`philosophy_doc_id`). Total project size
sits at ~175 files.

### How to verify

```bash
cd tank && source .venv/bin/activate
python -m pytest -q             # → 28/28
./scripts/start.sh              # → http://localhost:8000

# Visit the new pages:
#   /threat-models               — versioned TMs + drift detection
#   /decisions                   — decisions log
#   /design-reviews              — intake → checklist → approve
#   /postmortems                 — author + publish (creates followups)
#   /tabletops                   — scenario generator + lessons capture
#   /detections                  — Sigma rules + ATT&CK coverage
#   /compliance                  — control evidence map + gaps
#   /attack-surface              — weekly endpoint snapshot + diff
#   /lessons                     — searchable lessons DB
#   /glossary                    — company-jargon library
#   /me                          — ownership dashboard with risk score
#   /philosophy                  — curated security stance doc

# Try with sample data: open a Service entity (e.g. payments-api),
# click "I own this", then "Generate threat model (v2)". Then visit
# /threat-models to see drift detection ready for v2.
```


