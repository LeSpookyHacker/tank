# Changelog

All notable changes to Tank are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are in `YYYY-MM-DD` format.

For the full narrative build history with architectural rationale and tradeoff discussion, see [HISTORY.md](HISTORY.md).

---

## [Unreleased]

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
