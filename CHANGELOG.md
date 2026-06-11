# Changelog

All notable changes to Tank are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are in `YYYY-MM-DD` format.

For the full narrative build history with architectural rationale and tradeoff discussion, see [HISTORY.md](HISTORY.md).

---

## [Unreleased]

---

## [2026-06-11] — Philosophy freewrite refinement; security audit pass 8 fixes

### Added

- **Philosophy freewrite refinement** — a Vditor 3.10.9 rich-text editor is now embedded
  below the rendered philosophy doc at `/philosophy`. Type any ideas, lessons, or stance
  updates; click "Apply to philosophy" and Claude merges them into the existing document via
  `POST /api/philosophy/refine`. User text is passed through `apply_redactions()` before
  reaching the Anthropic API (privacy contract preserved). New prompt:
  `prompts/philosophy_refine.md`. New function: `app/claude/philosophy.py::refine()`. New
  endpoint: `POST /api/philosophy/refine` (rate-limited to 10/hour).

### Security

- Six findings from security audit pass 8 resolved. Full report:
  [`SECURITY-AUDIT-2026-06-11.md`](SECURITY-AUDIT-2026-06-11.md).
  - **SEC-007 (Low):** Repo ingest endpoint echoed blocked-path prefix in HTTP 403 body
    (`app/routers/ingest.py:157`). Now logs server-side and returns a generic message.
  - **SEC-008 (Medium):** `style-src 'unsafe-inline'` re-introduced for Mermaid SVG —
    accepted architectural trade-off; documented in code and CLAUDE.md. No code change.
  - **SEC-009 (Medium):** `onclick="closeRisk(...)"` in `risks.html` was silently blocked
    by CSP `script-src`, making the close button inoperative. Replaced with
    `data-action="close-risk" data-risk-id=…` + delegated listener.
  - **SEC-010 (Medium):** Six Claude-calling endpoints lacked `@limiter.limit()`: philosophy
    seed/evolve (3/hr), philosophy refine (10/hr), threat-model generate (5/hr), tabletop
    generate + generate-runbook (5/hr), security-program executive-brief (5/hr). All fixed.
  - **SEC-011 (Low):** Compliance wizard passed raw questionnaire answers to Claude without
    `apply_redactions()`. Fixed: answers are now redacted before `user_content` is assembled
    (`app/claude/compliance_wizard.py`).
  - **SEC-012 (Info):** LIKE wildcard passthrough in `find_for_technique()` — `%` and `_`
    in `attack_id` were interpreted as SQLite wildcards. Fixed: escape via `ESCAPE '\\'`
    before constructing the pattern (`app/kb/detections.py`).

---

## [2026-06-10] — Report formatting overhaul, plan generator fix, postmortem Vditor editor

### Fixed

- **Report double-spacing / excessive vertical whitespace** — `app/static/style.css` had
  `white-space: pre-wrap` on the second `.markdown-body` rule block. `marked.js` HTML output
  contains `\n` characters between block-level elements (`</h2>\n<ul>`, etc.); with `pre-wrap`
  those newlines rendered as visible ~14px-tall line breaks. Removing `white-space: pre-wrap`
  resolves double-spacing across all 9 templates that use `.markdown-body` (reports, threat
  models, policies, postmortems, IR runbooks, design reviews, philosophy, and tabletops).

- **Attack mapping button failure (HTTP 500)** — `attack_mapping()` in
  `app/claude/reports.py` raised `RuntimeError("attack_mapping returned no rows")` when no
  Threat Models existed in the KB, producing an HTTP 500 and a browser alert. Now renders a
  graceful "No data to map" blockquote explaining the prerequisite (run Threat landscape per
  service first) instead of crashing.

- **Risk register blank report** — When the risk register DB had no open entries, Claude
  returned a sparse `RiskRegisterReport` with `risks=[]`, rendering as a nearly blank page.
  `_render_risk_register()` now emits an actionable "No open risks found" blockquote.

- **Control coverage matrix all `?`** — When the KB lacked control-implementation evidence,
  Claude returned `"unknown"` for all cells (correct per the prompt instruction "when in doubt,
  choose unknown"). `_render_matrix()` now prepends an "Insufficient KB data" blockquote when
  > 70% of cells are `"unknown"`, explaining why coverage shows as `?`.

- **Plan generator — structured output error on empty response** — `plan_generator.py` used
  `parsed.output` which raises `AttributeError` if `messages.parse()` returns no structured
  output. Now uses `getattr(resp, "parsed_output", None)` with an explicit `None` check and a
  `RuntimeError` with a clear message.

### Changed

- **Report sub-items reformatted as compact inline bullets** — `_render_plan()`,
  `_render_state_of_security()`, `_render_initial_assessment()`, and
  `_render_program_roadmap()` previously used `### h3` headers for per-item sub-sections
  (actions, risks, findings, milestones). These are now inline bullet items
  (`- **Title** — desc · _attr: val_`), eliminating per-item h3 margin accumulation and
  cutting rendered page length by ~30%.

- **Plan generator — extended thinking removed, cache and token limit upgraded** —
  `app/claude/plan_generator.py` no longer passes `thinking={"type": "adaptive"}` (removes
  latency overhead). Cache control upgraded from `{"type": "ephemeral"}` to `CACHE_1H` for
  the system prompt block. `max_tokens` raised from 8192 → 16384.

- **Postmortem freewrite — Vditor Markdown editor** — the plain `<textarea>` on
  `/postmortems/new` is replaced with Vditor 3.10.9 (same as journal, notes, meeting prep).
  Custom toolbar, SRI-hashed CDN tags, dark/light theme-aware (`app/templates/postmortem_new.html`).

- **90-day plan generation — toast notification** — generating a new plan now shows a
  fixed-position toast ("Plan generation started!") with a 12s auto-dismiss instead of a
  simple spinner. Template bug fixed: `plan.items` → `plan['items']` (Jinja2 dict-access
  syntax, `app/templates/plan.html`).

- **Left-nav collapse button — overflow clip fix** — collapsed nav (`width: 0;
  overflow-x: hidden`) clipped the absolutely-positioned button off-screen. Switches to
  `position: fixed` in the collapsed state so it remains reachable at the left edge.

- **`scripts/stop.sh` — multi-PID handling** — `lsof` can return multiple PIDs when uvicorn
  forks workers. The script now normalises `$PID` into an array, sends `SIGTERM` to all, and
  checks whether any process is still alive during the 5s graceful-shutdown loop.

---

## [2026-06-09] — Vditor markdown editor in risk management UI

### Changed

- **Vditor editor on risk management pages** — the plain textareas on the risk register entry
  form (description, context, notes, treatment rationale fields) are replaced with the same
  Vditor 3.10.9 rich Markdown editor used in the journal, notes, and meeting prep pages:
  IR mode, custom toolbar (bold, italic, headings, lists, code blocks, links), SRI-hashed
  CDN tags, and dark/light theme-aware (`app/templates/risk_detail.html`,
  `app/templates/risk_form.html`).

---

## [2026-06-08] — DFD diagram rendering fix (skeleton loaders, Mermaid securityLevel, CSP §8.3.2)

### Fixed

- **DFD workspace completely unusable** — three-layer bug: skeleton loading bars never hid,
  and all node shapes, severity colors, and data-flow edges were invisible (only floating
  white text labels in a black void).
  - **Layer 1 (skeleton loaders):** `app/static/style.css` had `display: flex` on
    `.dfd-diagram-skeleton` / `.dfd-findings-skeleton`; author stylesheets override the
    browser's `[hidden] { display: none }` rule. Fix: explicit `[hidden]` compound-selector
    override in `style.css`.
  - **Layer 2 (Mermaid `securityLevel: 'strict'`):** Mermaid v11 internally calls
    `DOMPurify.sanitize` for `strict` and `antiscript` modes, stripping every inline
    `style="fill:..."` attribute from SVG shapes and the entire `<style>` theme block.
    Fix: `securityLevel: 'loose'`, which skips the DOMPurify pass. Tank is local-only;
    XSS from Mermaid diagram content is not a threat.
  - **Layer 3 (CSP §8.3.2 nonce + `unsafe-inline`):** Per CSP3 §8.3.2, when any `nonce-*`
    is present in `style-src`, browsers silently ignore `'unsafe-inline'` for `<style>`
    ELEMENTS. Mermaid's runtime-generated `<style>` block (inserted via `innerHTML`) can
    never receive a nonce, so it is always blocked regardless of `unsafe-inline`.
    Fix: `applyTankTheme(container)` (in `dfd_detail.html`) and `applyPreviewTheme(container)`
    (in `dfd.html`) walk the SVG DOM and call `element.style.setProperty()` from
    nonce-protected `<script>` blocks after inserting the SVG. JS DOM style manipulation
    is governed by `script-src` only, not `style-src`. `applyTankTheme` is severity-aware:
    reads `_elementThreatMap` to pick per-node fill colors matching the STRIDE severity
    palette (Critical `#DC2626`, High `#EA580C`, Medium `#D97706`, Low `#4F46E5`).
    Nodes with no threats get the default Tank purple (`#2d1b6e` fill, `#7c3aed` stroke).
- **Dark-theme Mermaid color variables corrected** — `primaryColor` was `#1a1728`
  (essentially invisible against `#0d0d12` background, 1.38:1 contrast ratio) →
  `#2d1b6e`; `lineColor` `#6c5ce7` → `#9d8df1`; `primaryBorderColor` `#3d2e6b` →
  `#7c3aed`. `applyTankTheme` owns these values; `themeVariables` remain as a fallback
  for light mode and print.

---

## [2026-06-08] — Security hardening: audit pass 7 (6 findings)

### Security

- Six findings from audit pass 7 resolved. Full report: [`SECURITY-AUDIT-2026-06-08.md`](SECURITY-AUDIT-2026-06-08.md).

---

## [2026-06-05] — Security hardening: audit pass 6 (34 findings)

### Security

- Thirty-four findings from audit pass 6 resolved. Full report: [`SECURITY-AUDIT-2026-06-05.md`](SECURITY-AUDIT-2026-06-05.md).

---

## [2026-06-04] — Security hardening: audit pass 5 (16 findings)

### Security

- Sixteen findings from audit pass 5 resolved. Full report: [`SECURITY-AUDIT-2026-06-04.md`](SECURITY-AUDIT-2026-06-04.md).

---

## [2026-06-04] — Meeting prep fix, stack audit tool dropdown, Vditor editor for Notes & Meeting Prep

### Fixed

- **Meeting prep 400 error** — `meeting_prep.prepare()` called `build_scope_block()` which
  returns `CACHE_1H = {"type": "ephemeral", "ttl": "1h"}`. Haiku rejects the 1h extended TTL;
  the Anthropic API returned 400 on every "Prepare brief" click. Both the sync and batch paths
  now override the scope block's cache control to `CACHE_5M`, matching every other Haiku call
  in the codebase (`app/claude/meeting_prep.py`).

### Changed

- **Security Stack Audit — Current Tool dropdown** — the free-text "Current Tool" input is
  replaced with a per-category dropdown pre-populated with 5–7 common tools (e.g., Okta /
  Azure AD / JumpCloud for Identity Provider; CrowdStrike / SentinelOne / Defender for EDR).
  Selecting "Other…" reveals a text input for custom values. Existing saved tool names are
  matched on load; unrecognized values auto-select "Other" and pre-fill the custom input
  (`app/routers/stack_audit.py` — `TOOL_OPTIONS`; `app/templates/stack_audit.html`).
- **Vditor Markdown editor for Notes and Meeting Prep** — the plain textareas on `/notes`
  and `/meeting-prep` are replaced with the same Vditor 3.10.9 rich editor used in the
  journal: IR mode, custom markdown toolbar (bold, italic, headings, lists, code, links),
  SRI-hashed CDN tags, dark/light theme-aware. Notes gets 360px min-height; meeting prep
  extras gets 200px. CSS override on the notes page reduces Vditor's default horizontal
  padding so text starts at the left edge (`app/templates/notes.html`,
  `app/templates/meeting_prep.html`).

---

## [2026-06-04] — Journal redesign (rich editor, per-entry pages, titles)

### Changed

- **Rich Markdown editor** (Vditor) replaces the previous plain textarea on the journal entry page.
  Supports headings, bold/italic/strikethrough, bullet/ordered lists, blockquotes, inline code,
  code blocks, and links via a custom toolbar.
- **Per-entry pages** at `/journal/{entry_id}` with breadcrumb navigation.
  `GET /journal/today` redirects to today's entry page; `GET /journal` is now an entry-list index.
- **Optional title per entry** — new `title TEXT` column in `journal_entries`
  (added by `_migrate_journal_title` in `app/db.py`); shown in the list and in the page `<title>`.
- Entry list cards show the title (or "(untitled)" fallback) and link directly to the entry page.

---

## [2026-06-03] — Kanban board generator (replaces flat follow-ups list)

### Added

- **Kanban board generator** at `/kanban`: landing page shows a grid of board tiles (title, description, per-column card counts). Each tile links to a full board view at `/kanban/boards/{id}`.
- Per-board view with three columns — **TODO**, **Doing**, **Done** — and SortableJS drag-and-drop between columns. Card order persists via `POST /api/kanban/boards/{id}/reorder`.
- Cards support inline title + optional note editing (click to edit, blur to save via `PUT /api/kanban/cards/{id}`). Delete button (×) shown on hover.
- "Add card" form at the bottom of each column; board title and description are click-to-edit in the board header.
- Delete board button (with JS confirmation); cascades to all cards.
- New DB tables: `kanban_boards`, `kanban_cards` (migrated by `_migrate_kanban` in `app/db.py`).
- New storage module: `app/storage/kanban_store.py`.
- New router: `app/routers/kanban.py` (page routes + `/api/kanban/*` REST API).

### Changed

- Nav label "Follow-ups" → **Kanban**; `/followups` route redirects replaced by `/kanban` everywhere in the UI and docs.
- All user-facing "Follow-ups" / "follow-ups" text updated to "Kanban" across templates, docs, and CLAUDE.md.

### Preserved (backward compat)

- `followups` table, `app/storage/followups_store.py`, and `/api/followups` endpoints unchanged — postmortem action-item auto-creation, the Today home widget, and me-page scoring all continue to work.

---

## [2026-05-29] — Security hardening: adversarial audit pass 4 (fresh full re-audit)

### Security

**Pass 4 — Sensitive-path guard, SQL identifier validation, fresh full re-audit (3 code fixes + 5 documented findings)**

- **VULN-P4-01 (Medium):** Sensitive-path blocklist gap on one-off ingest — `POST /api/ingest/path` and `POST /api/ingest/repo` allowed any path under `Path.home()`, including `~/.ssh`, `~/.aws/credentials`, and `~/.tank/db.sqlite`. Factored shared guard into `app/ingest/path_guard.py::is_blocked_path()` covering `/etc /proc /sys /dev ~/.ssh ~/.gnupg ~/.aws ~/.tank ~/.config`; called from both ingest endpoints and the folder-watcher target validator (`integrations.py`), replacing the watcher's inline blocklist. Tests in `tests/test_ingest_path_guard.py`.
- **VULN-P4-02 (Low):** SQL identifier injection regression risk in `app/db.py::_add_col_safe` — `table` parameter was interpolated into `PRAGMA table_info({table})` and `ALTER TABLE {table}` without validation. Added `re.fullmatch` guard; raises `ValueError` for any non-identifier table name.
- **VULN-P4-03 (Low):** SQL identifier injection regression risk in `app/storage/teams_store.py::update_team` and `app/storage/projects_store.py::update_project` — both build `UPDATE` SET clauses from `**kwargs` keys via f-string interpolation; keys were allowlisted but not separately validated. Added `_SAFE_IDENT` regex assertion after allowlist filtering.
- **VULN-P4-04 (Medium, documented only):** CSP `script-src 'unsafe-inline'` weakens XSS defense; removal requires nonce migration across ~20 templates — deferred as a planned sprint.
- **VULN-P4-05 (Low, documented only):** GitHub token accepted in POST body of `POST /api/discovery/github-scan` — may appear in access logs; recommend `Authorization: Bearer` header or `TANK_GITHUB_TOKEN` env var.
- **VULN-P4-06 (Info, fixed):** Architecture images sent unredacted to Anthropic API during vision extraction — by design, but now disclosed. `app/templates/ingest.html` shows a privacy notice banner automatically when PNG/JPG files are selected. `app/templates/dfd.html` existing image notice updated to include the same privacy language. CSS added for the notice style.
- **VULN-P4-07 (Info, documented only):** Unpinned `>=` dependency versions in `requirements.txt` — recommend lock file for production.
- **VULN-P4-08 (Info, documented only):** Prompt injection via ingested documents — mitigated by `_KB_TRUST_HEADER` in `caching.py`; inherent LLM limitation noted.

**Re-confirmed intact from passes 1–3 (34 prior fixes verified):** API-key gate, CSRF on wipe, ICS SSRF guard, cve/github/discovery SSRF (hardcoded domains), SQL parameterization, FTS5 phrase-quoting, command injection absence, safe YAML deserialization, upload path traversal, symlink traversal (folder watcher), XSS (DOMPurify on all markdown templates), ReDoS (SIGALRM timeout), placeholder format injection, redaction completeness across all Claude call sites, UUID4 IDs, DoS size/depth bounds, no committed secrets.

Full findings report: [`docs/security/audit-pass-4.md`](security/audit-pass-4.md)

---

## [2026-05-27] — Security hardening: adversarial audit passes 1–3 (34 vulnerabilities)

### Security

**Pass 1 — Authentication, CSRF, headers, cleanup (11 findings)**

- **VULN-001 (High):** Added `TANK_API_KEY` middleware — when the env var is set, all requests except `/healthz` and `/static/*` require an `X-Tank-Key` header; uses `secrets.compare_digest` to prevent timing attacks (`main.py`)
- **VULN-002 (High):** CSRF hardening on `/api/wipe` — now requires `X-Confirm: delete-tank` custom header; browsers cannot forge custom headers in cross-site form submissions (`settings.py`)
- **VULN-003 (Medium):** ReDoS prevention — custom redaction patterns now validated via `signal.SIGALRM` with a 1-second deadline; tests run at 40, 100, and 200 chars of adversarial `a...!` input to catch patterns that pass short-string tests but backtrack catastrophically on longer inputs (`redact/config.py`)
- **VULN-004 (Medium):** SSRF / DNS rebinding — ICS watcher now resolves DNS once, stores the IP, and passes it via `urllib.request.Request` with an explicit `Host` header; added `ipv4_mapped` check for IPv4-mapped IPv6 addresses (`ics.py`)
- **VULN-005 (Medium):** Prompt injection labeling — KB chunks now wrapped in a structural delimiter in the system prompt marking them as untrusted user data (`claude/caching.py`)
- **VULN-006 (Medium):** LLM tool-use cap surfaced — chat loop iteration-cap warning now emitted as a user-visible SSE event in addition to the server log (`claude/chat.py`)
- **VULN-007 (Medium):** CSP `fonts.googleapis.com` removed from `script-src` — it serves fonts, not scripts; `style-src` unchanged (`main.py`)
- **VULN-008 (Low):** Temporary ingest files cleaned up — `_do_ingest_file` now deletes the temp directory in a `finally` block after every ingest attempt, success or failure (`routers/ingest.py`)
- **VULN-009 (Low):** `placeholder_fmt` format-string injection — custom redaction rule placeholder validated against `^\[?[A-Z0-9_]+\{n(?::\d+d)?\}\]?$` before storage (`redact/store.py`, `routers/settings.py`)
- **VULN-010 (Low):** Added `Strict-Transport-Security` and `Permissions-Policy` headers to `_SecurityHeadersMiddleware` (`main.py`)
- **VULN-011 (Info):** `tenure_day` removed from `/healthz` response to avoid leaking internal state to any network-exposed probe

**Pass 2 — Privacy contract, parser bombs, input bounds (10 findings)**

- **Redaction bypass (High):** Reports scope block (`_build_scope_block`), `questions_for()`, and `risk_register()` now call `apply_redactions()` on entity names, descriptions, and owner names before Claude calls (`claude/reports.py`)
- **Parser bomb (Medium):** Ingest pipeline hard-caps file size at 50 MB before any parsing begins (`ingest/pipeline.py`)
- **Parser bomb (Medium):** PDF parser capped at 2,000 pages; `PdfReader` wrapped in try/except to handle malformed archives gracefully (`ingest/parsers/pdf.py`)
- **Parser bomb (Medium):** DOCX parser wraps `docx.Document()` in try/except; malformed ZIP archives (decompression bombs) are caught and return an empty `ParsedDocument` (`ingest/parsers/docx.py`)
- **Parser bomb (Low):** CSV parser bounded at 50,000 rows to prevent memory exhaustion on large dumps (`ingest/parsers/csv_json.py`)
- **Input bounds (Low):** Entity graph endpoints: `limit` 1–1000, `hops` 1–5, `depth` 1–5 (`routers/entities.py`)
- **Input bounds (Low):** Decisions endpoints: `within_days` 1–365, `days` 1–730 (`routers/decisions.py`)
- **Input validation (Low):** Tabletop `threat_kind` capped at 200 chars, `scenario_hook` at 1,000 chars (`routers/tabletops.py`)
- **Watcher SSRF (Medium):** Integrations router validates watcher kind against an allowlist (`folder`, `ics_url`, `cve_feed`, `github_repo`); folder watcher target validated against blocked system directories (`/etc`, `/proc`, `/sys`, `/dev`, `/root`, `~/.ssh`, `~/.gnupg`) (`routers/integrations.py`)
- **UI security:** `X-Tank-Key` header injected into all `fetch()` calls and `EventSource` connections by `base.html`; key read from `localStorage` and settable via a new Settings field

**Pass 3 — Redaction bypasses, FTS5 injection, symlink traversal, secret patterns (13 findings)**

- **Redaction bypass (Medium):** Threat model scope block redacts entity names and descriptions (`claude/threat_modeling.py`)
- **Redaction bypass (Medium):** Decisions context redacts document titles before Claude calls (`claude/decisions.py`)
- **Redaction bypass (Medium):** Tabletop scenario prompt redacts entity card names and descriptions (`claude/tabletop.py`)
- **Redaction bypass (Medium):** Meeting prep brief redacts attendee, time, and extras fields (`claude/meeting_prep.py`)
- **Redaction bypass (Medium):** Philosophy doc context redacts decision titles (`claude/philosophy.py`)
- **Redaction bypass (Medium):** ATT&CK attack mapping redacts threat titles, descriptions, and service names (`claude/attack_mapping.py`)
- **Redaction bypass (Medium):** IAM translator redacts policy entity names and descriptions (`claude/iam_translator.py`)
- **Symlink traversal (Medium):** Folder watcher scan phase resolves symlinks and skips files whose resolved path escapes the watched directory root (`ingest/watchers/folder.py`)
- **FTS5 operator injection (Medium):** Full-text search queries wrapped in `"..."` phrase quotes (inner `"` doubled) to prevent AND/OR/NOT/`*` operator injection changing query semantics (`kb/search.py`)
- **Dead code / logic bug (Low):** `graph_for_type()` BFS now correctly respects the `depth` parameter (was dead code before); entity graph traversal properly bounded at the requested depth (`kb/relationships.py`)
- **Secret detection expansion (Medium):** Added 5 new regex patterns to `_EXTRA_SECRET_RES`: AWS STS session keys (`ASIA[A-Z0-9]{16}`), GitHub fine-grained PATs (`github_pat_...`), GitHub classic PATs (`ghp_...`), GCP API keys (`AIza...`), Azure connection strings (`redact/secrets.py`)
- **Input bounds (Low):** Nudge snooze hours 1–8760; journal recent days 1–365; attack-surface history limit 1–100; lessons days 1–1825 and limits bounded (`routers/nudges.py`, `routers/journal.py`, `routers/attack_surface.py`, `routers/lessons.py`)
- **Input validation (Low):** Onboarding cadence `digest_time` validated against `HH:MM` pattern; `reflection_day` restricted to valid weekday names via `Literal` (`routers/onboarding.py`)

---

## [2026-05-27] — Security audit pass 2

### Security

- **VULN-001 (Critical):** Redact Mermaid source, description text, document content, and project notes before all Claude DFD calls (`dfd_analyzer.py`)
- **VULN-002 (High):** SSRF fix — ICS hostname validation now resolves DNS and checks every returned IP against RFC-1918/loopback ranges (`ics.py`)
- **VULN-003 (High):** XSS fix — removed server-side `| safe` render in IR runbook detail; client-side DOMPurify required (`ir_runbook_detail.html`)
- **VULN-010 (High):** DFD upload endpoints capped at 20 MB (`dfd.py`)
- **VULN-004 (Medium):** Removed `fonts.googleapis.com` from `script-src` CSP — it serves fonts, not scripts (`main.py`)
- **VULN-005 (Medium):** Repo ingest endpoint now validates path with `.resolve()` + allowlist check, matching existing ingest pattern (`ingest.py`)
- **VULN-006 (Medium):** Nyx intake endpoint returns 503 when `TANK_NYX_API_KEY` is unset instead of silently accepting all requests (`risks.py`)
- **VULN-007 (Medium):** Exception details no longer sent to SSE stream or HTTP response; generic messages used instead (`chat.py`, `security_program.py`)
- **VULN-008 (Medium):** Custom redaction rules now reject patterns with nested quantifiers or quantified alternation (ReDoS prevention) (`redact/config.py`)
- **VULN-012 (Medium):** XSS fix — `| safe` removed from design review, postmortem, tabletop, and threat model detail templates; client-side marked + DOMPurify
- **VULN-013 (Medium):** XSS fix — philosophy page `| safe` removed
- **VULN-014 (Medium):** XSS fix — report detail unsafe DOMPurify fallback removed
- **VULN-009 (Low):** `tenure_day` removed from `/healthz` response (internal state, not for public consumption)
- **VULN-011 (Low):** Images larger than 20 MB skipped before vision API call
- **VULN-015 (Low):** ICS response read capped at 10 MB
- **VULN-016 (Low):** `VulnerabilityIntake.cve_id` now validated against `CVE-YYYY-NNNN` format

---

## [2026-05-27] — Risk register, security program dashboard, IR runbooks

### Added

- **Risk register** (`/risks`) — formal inherent/residual 1–5 L×I scoring, treatment strategies (mitigate/accept/transfer/avoid), Sonnet KB-grounded assessment, 90-day review scheduling
- **Security program dashboard** (`/security-program`) — 6-domain KPI aggregation, on-demand executive brief with green/yellow/red health indicator, weekly 12-week trend snapshots
- **IR runbooks** (`/ir-runbooks`) — per-service, per-scenario 5-phase incident-response playbooks (Detect/Contain/Eradicate/Recover/Comms) grounded in KB; integrated with tabletops and postmortems
- `get_risk_register` and `find_ir_runbooks` chat tools
- `risk_register` added to `REPORT_REGISTRY` for scheduled reports
- `risk_review_due` and `missing_ir_runbook` nudge kinds
- Nyx vulnerability intake endpoint (`POST /api/vulnerabilities/intake`) for [Nyx](https://github.com/LeSpookyHacker/nyx) integration
- Sunday 09:30 security program snapshot scheduler job

---

## [2026-05-26] — Sample data expansion (3.4)

### Added

- 16 new files in `sample_data/`: identity service detail, PII vault detail, team CSV, secrets policy, PII breach runbook, 3 Sigma detection rules, 2 IAM policies, NIST CSF 2.0 fragment, 4 DFD Mermaid source files, additional postmortems
- `scripts/seed_db.py` — idempotent DB seed (org, teams, projects, DFD analyses, decisions, glossary, lessons, tabletop, journal, follow-ups) without API cost
- `sample_data/README.md` complete rewrite with full file inventory and verification checklist

---

## [2026-05-26] — DFD threat modeling revamp (3.2 rewrite)

### Changed

- **DFD pipeline** rebuilt as a three-stage professional workflow: four input modes (paste Mermaid, upload file, from document, from description) → 4-step SSE progress tracker → split-panel interactive workspace
- `DFDThreat` schema gains `threat_id`, `element_label`, `title`, `cvss_estimate`, `references`

### Added

- Generate-from-description and generate-from-document endpoints
- SSE-tracked DFD analysis (`POST /api/dfd/start-analysis` → `task_id`)
- Interactive split-panel workspace: clickable diagram nodes, threat-card cross-linking, zoom, severity + STRIDE filter pills
- PDF export via `@media print` CSS (cover, diagram SVG, threat table, STRIDE 6×4 matrix, Mermaid appendix)
- Annotated `.mmd` export with severity `style` directives
- `--sev-critical/high/medium/low` CSS variables as single source of truth for severity colors
- Project context injection into DFD analysis prompts

---

## [2026-05-25] — Projects dashboard (3.3)

### Added

- Projects card dashboard with color accent, emoji, description, active badge, and last-opened memory
- `color` and `notes` fields on projects; `<input type="color">` picker; inline edit without page reload
- Project detail page with scoped doc/conversation/report counts
- Project notes injected into system prompt for project-scoped chat conversations

### Fixed

- Home route now validates `active_project_id` on every request; auto-resets to Default if project was deleted

---

## [2026-05-25] — Token tracking, Haiku extraction, Markdown reports, nav redesign (2.1 / 2.2 / 2.3 / 3.1)

### Fixed

- **Token cost undercount** — `reports` table now stores `cache_read_in` / `cache_create_in`; 13+ previously-untracked Claude modules now call `log_token_usage()`; `/api/usage/cost` aggregates from all three tables (`messages`, `reports`, `api_calls`)

### Changed

- Entity extraction, meeting prep, journal/lesson extraction, and nudge generation switched from Sonnet to `claude-haiku-4-5-20251001` (~10× lower cost for structured JSON tasks)
- Reports now render Markdown via `marked.js` instead of `<pre>` tags
- Navigation redesigned from topbar to grouped left sidebar (Workspace / Pipeline / Workstreams / System)

### Added

- PDF and Markdown download export for all reports
- `TANK_DEBUG_TOKENS=1` env var for per-call token logging
- `api_calls` table to capture spend from modules not previously tracked
- Empty-state component on home dashboard
- DFD threat modeling (initial version — superseded by 3.2 rewrite)

---

## [2026-05-22] — Phases 11–15: continuous-ingestion connectors, living artifacts, workstreams, coverage, second brain

### Added

- **Phase 11 — Connectors:** folder watcher, ICS calendar importer, CVE feed, GitHub repo connector (Settings → Integrations)
- **Phase 12 — Living threat models + decisions log:** versioned, drift-aware threat models per service; `arch_snapshot_hash` drift detection; decisions log with kinds (design_choice, accepted_risk, deferred_fix, security_invariant), expiry tracking, reaffirmation
- **Phase 13 — Workstreams:** design reviews (freewrite → checklist → approval → decisions); postmortems (freewrite → structured fields → followups + lessons); tabletop exercises (scenario + injects + rubric + lessons)
- **Phase 14 — Coverage + visibility:** Sigma detection rules ingest; IAM policy ingest (AWS/K8s RBAC/GCP); control framework ingest (JSON); ATT&CK coverage map; IAM policy translator; compliance evidence collection; weekly attack-surface snapshot + diff
- **Phase 15 — Second brain:** lessons-learned DB (auto-populated from postmortems, tabletops, rejected design reviews); glossary builder; personal ownership dashboard with per-entity risk scoring; security philosophy doc (seeded Day-30, evolved at Day-60/90/180/365); security-focused anniversary retros

---

## [2026-05-21] — Phases 6–10: chat, reports, partner mode, UI, privacy assertion

### Added

- **Phase 6 — Chat:** SSE-streamed chat with tool use; 15 KB tools; citations on every reply; persistent side panel on all pages; full-screen `/chat`
- **Phase 7 — Reports:** 6 original report kinds with shared cached scope block; `REPORT_REGISTRY` dispatch; subscription cadence; `2.1` adds Markdown rendering + PDF/MD export
- **Phase 8 — Partner mode:** morning digest, evening journal prompt, Friday weekly reflection, Day-30/60/90/180/365 anniversary retrospectives; follow-ups; nudge system (8 kinds)
- **Phase 9 — UI:** entity graph; settings page; provenance trust badges; Nyx-inspired dark/light theme; side-panel chat
- **Phase 10 — Privacy assertion:** `scripts/verify_privacy.py` — scans all redacted columns for planted fixture identifiers; exit 0 = pass

---

## [2026-05-21] — Phases 3–5: ingest pipeline, KB retrieval, parsers

### Added

- **Phase 3 — Ingest pipeline:** orchestrated `parse → chunk (800/120) → redact → embed (local all-MiniLM-L6-v2) → FTS5 + sqlite-vec → entity extraction via Claude → entity/relationship upsert`
- **Phase 4 — KB layer:** hybrid retrieval (sqlite-vec ANN + FTS5 BM25, reciprocal rank fusion); 6 initial chat tools; entity cards; prompt caching (system block + KB block)
- **Phase 5 — Parsers:** PDF (`pypdf`), DOCX (`python-docx`), vision diagram extraction (Sonnet), CSV/JSON (CMDB, IAM, control frameworks, Sigma rules), repo summary (no raw source ever sent)

---

## [2026-05-20] — Phases 1–2: foundation, redaction engine

### Added

- Project skeleton: FastAPI app, SQLite schema (17 tables), uvicorn server, `scripts/start.sh` / `stop.sh`
- **Redaction engine** with 11 categories: email, internal hostname (custom TLD + defaults), private IPv4 (RFC1918/loopback/link-local/CGNAT), AWS account IDs, AWS ARNs, GCP project IDs, Azure subscriptions/tenants, secret tokens (one-way SHA-256 hashed), and optional person names
- 28 redaction unit tests (determinism, dedup, overlap resolution, rehydration, one-way hashing, custom rules)
- Helix Robotics synthetic sample data set (26 files, 2 repos)
- Operations layer: durable scheduler state (SQLite), TZ-aware scheduler, weekly SQLite backup, Anthropic SDK retry config, `/healthz` endpoint, systemd unit + install script
