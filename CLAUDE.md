# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Tank is

Tank is a **local-first, privacy-preserving** onboarding *and*
daily-companion partner for new Sr/Staff/Manager security engineers.
Users feed it their employer's architecture docs, source repos, CMDB,
people info, Sigma detection rules, IAM policies, and control
frameworks. Tank redacts internal hostnames/emails/IPs/secrets
locally, builds a typed knowledge graph, and uses Claude Sonnet 4.6
for:

- Chat with 15 tools over the KB.
- 14 report kinds (threat landscape, cross-service gaps, 30/60/90,
  stakeholder map, questions-for-team, control matrix, on-call
  handoff, weekly security digest, ATT&CK mapping, IAM audit,
  risk register, state of security, initial assessment, program roadmap).
- Living artifacts: versioned threat models (drift-aware), decisions
  log, design reviews, postmortems, tabletops, IR runbooks, policies
  (5 kinds), 90-day plan.
- Partner mode: Day-1 brief, journal, follow-ups, recurring reports,
  anniversary retros (generic + security-focused), philosophy doc.
- Second brain: lessons-learned DB, glossary, ownership dashboard,
  tenure-aware lens (map / prioritize / execute / maintain).
- Security program dashboard: aggregated health metrics, executive
  brief, weekly snapshots, compliance wizard.
- Risk register + vulnerability triage: CRUD risk register, vuln
  intake queue with triage/assign/promote-to-risk workflow.
- First-hire onboarding: intake interview (seeds entity stubs),
  GitHub/team discovery, stack audit, 90-day plan generator.

The **headline guarantee** is non-negotiable: nothing reaches the
Anthropic API in cleartext. Everything passes through
`app/redact/engine.py` first. Secrets are one-way SHA-256 hashed;
they cannot be rehydrated even internally.

The full build history (what was shipped per phase, what tradeoffs
were taken, known gaps) lives in [HISTORY.md](HISTORY.md). Read it
for context before making structural changes.

The user-facing documentation lives in [docs/](docs/) — installation,
onboarding walkthrough, per-feature reference, operations, FAQ,
troubleshooting. When the user asks a question that's covered there,
point them at the relevant doc instead of paraphrasing.

## Commands

```bash
# First-time setup (idempotent on re-runs)
./scripts/start.sh                  # creates .venv, installs deps, inits DB,
                                    # boots uvicorn with first-run banner

# Tests
python -m pytest -q                 # whole suite (28 redaction tests today)
python -m pytest tests/test_redaction.py::test_email_redacted -v   # one test
python -m pytest -k "secret" -v     # match by name

# Ingest sample data (after start.sh once + .env has ANTHROPIC_API_KEY)
python -m scripts._gen_fixtures     # synthesize PDF/DOCX/PNG from MD sources
python -m scripts.load_fixtures --dry-run   # print plan, no ingest
python -m scripts.load_fixtures             # actual ingest (uses API key)
python -m scripts.ingest_cli <path> --category architecture     # one-off

# Privacy assertion (run after ingest)
python -m scripts.verify_privacy --fixture-pack
# → scans the DB for any planted identifier that leaked into a
#   redacted-text column. Exit 0 = pass, 1 = fail.

# DB inspection
sqlite3 ~/.tank/db.sqlite "SELECT category, COUNT(*) FROM redaction_map GROUP BY category;"

# Debug token usage — logs per-call in/out/cache_read/cache_create to console
TANK_DEBUG_TOKENS=1 uvicorn app.main:app --reload

# Ops: healthcheck (works without an API key)
curl http://127.0.0.1:8000/healthz

# Ops: inspect scheduler state (last-fired markers, durable across restarts)
sqlite3 ~/.tank/db.sqlite \
  "SELECT job_name, last_label,
          datetime(last_fired_at,'unixepoch','localtime')
   FROM scheduler_state ORDER BY job_name;"

# Ops: inspect backup ledger (weekly snapshots, retention 8)
sqlite3 ~/.tank/db.sqlite \
  "SELECT path, size_bytes,
          datetime(created_at,'unixepoch','localtime')
   FROM backup_log ORDER BY created_at DESC LIMIT 8;"

# Ops: manually trigger a backup (otherwise Sun 03:00)
python -c "from app.claude.scheduler import _take_backup; _take_backup()"

# Stop the server (graceful shutdown via SIGTERM)
./scripts/stop.sh

# Ops: install as a systemd --user unit (Linux only)
./scripts/install-systemd.sh
```

`./scripts/start.sh` enforces Python 3.11+. The codebase **runs on
3.9** (this dev box has only 3.9) because Pydantic 2 + a vendored
`eval_type_backport` make the union syntax work; production target
stays 3.11+ so `sqlite-vec` can load.

## Architecture

### The privacy contract drives every data flow

```
parse → CHUNKER → REDACT  →  SQLite                  →  Anthropic API
                                  ↓ retrieve              ↑ (redacted)
                              cached KB block             rehydrate locally
                                  ↓
                              prompt assembly
```

`app/redact/engine.py::apply_redactions(text)` is the single chokepoint.
Every byte that reaches Claude has been through it. Chunks are
pre-redacted at ingest time (not at send time) — `chunks.text_redacted`
is what flows out; `chunks.text_original` is local-only forensics.
**If you add a new code path that calls Claude, run user text through
`apply_redactions` first and rehydrate the response with
`rehydrate(text, load_rehydration_map(used_placeholders))`.**

`redaction_map.original_text` holds the SHA-256 hash, not cleartext,
for `category='secret_token'` — secrets can't be rehydrated by design.
Every other category is reversible.

### The three big subsystems

**1. Ingest pipeline** (`app/ingest/`) — orchestrator
`pipeline.py::ingest(path, category)` runs:
`parse → chunk (RecursiveCharacterTextSplitter + tiktoken, 800/120) →
redact → bulk_insert_chunks + FTS5 + sqlite-vec → entity extraction via
Claude messages.parse → entity/relationship upsert`. Repos go through
`ingest_repo()` → `code_facts.summarize()` (no raw source ever sent;
only the structured summary + README).

Parsers are dispatched by extension in `app/ingest/parsers/__init__.py`
to `markdown.py | pdf.py | docx.py | csv_json.py | image.py`. The
image parser calls Sonnet vision (`app/claude/extractor.py::extract_from_diagram`)
and stashes the result in `meta["vision"]`; the extractor module
persists it without re-prompting. All parsers extend `_base.py`.

Entity extraction (`app/claude/extractor.py`) is rate-limited by a
module-level `threading.Semaphore(2)` — at most 2 Claude calls in
flight across all concurrent background ingest tasks. On 429 responses
it retries with delays `[5, 15, 30, 60, 120]` seconds before giving up.
This is especially important during bulk folder ingests.

Every extracted entity carries `provenance ∈ {source, inferred, claim,
user}` — set at upsert time, shown as a trust badge in the UI, and
queryable. `source` = stated in a doc; `inferred` = Sonnet concluded
it; `claim` = unverified assertion; `user` = manually added.

**2. Chat with SSE + tool use** (`app/claude/chat.py`,
`app/routers/chat.py`) — pioneers both patterns in this codebase.

`run_turn(conv_id, user_text)` is an async function that:
1. Redacts the user message.
2. Embeds locally (sentence-transformers all-MiniLM-L6-v2).
3. Hybrid retrieves (vec + FTS5 + reciprocal rank fusion in `app/kb/search.py`).
4. Pulls entity cards for top entities cited.
5. Builds `messages.stream(...)` with cached system + cached KB block
   + history.
6. Stream-loops: text deltas → SSE events; `tool_use` blocks →
   `app/kb/tools.py::execute_tool(name, args)` → tool_result → continue
   until `end_turn`.
7. Rehydrates, persists `redacted_view` (audit) and `display_view` (UI).

The HTTP shape: `POST /api/conversations/{id}/messages` kicks off an
asyncio.Task that drains events into a per-conversation queue. The
browser's `EventSource` subscribes via `GET .../stream`. Reconnect-safe.

The Anthropic SDK streaming context manager is synchronous, so the
chat loop runs it via `loop.run_in_executor(None, _run_stream)`.
Events are bridged to the asyncio side via `app/claude/event_bus.py`.

**3. Reports** (`app/claude/reports.py`) — six generators sharing a
cached scope block (`_build_scope_block`). Running all six against the
same global scope reuses the prompt cache — ~2× cheaper than cold runs.
Each generator: `messages.parse(output_format=PydanticClass)` → render
markdown → persist both redacted (audit) + rehydrated (display) in
the `reports` table. `REPORT_REGISTRY` in `reports.py` is the dispatch
table the router and scheduler both use.

### Partner mode: the daily-companion machinery

Lives across `app/claude/{nudges,meeting_prep,notes,day1_brief,anniversary,journal_extractor,scheduler}.py`
and `app/storage/{journal,followups,subscriptions,usage,nudges,notes}_store.py`.

The **scheduler** is a single `asyncio.Task` started in
`app/main.py::lifespan` and cancelled on shutdown. It wakes every 60s
and dispatches:

- Daily at `app_state.digest_time` → regenerate nudges (8 kinds,
  rate-limited to 2/day), run due `report_subscriptions`, anniversary
  check at days 30/60/90/180/365.
- `reflection_day` 16:00 (default Friday) → weekly reflection trigger.
- Weekday 18:00 → journal-prompt nudge if no entry today.
- Daily 22:00 → auto meeting-prep briefs for tomorrow's ICS meetings
  (rate-limited to 5/day).
- Sunday 09:00 → attack-surface snapshot (diffs against prior week).
- Sunday 09:30 → security-program metrics snapshot.
- Sunday 03:00 → weekly SQLite backup.

The **tenure lens** (`app/role.py::current_lens()`) returns
`map | prioritize | execute | maintain` based on
`app_state.tenure_started_at`. Chat system prompts read this and load
`prompts/chat_lens_<lens>.md` to shift framing. **Same KB, different
lens.**

### Where things live, by purpose

| You want to | Look in |
| --- | --- |
| Change how something gets redacted | `app/redact/rules.py` (categories), `app/redact/secrets.py` (detect-secrets + entropy fallback) |
| Add a new parser | `app/ingest/parsers/<kind>.py` + register in `parsers/__init__.py::_BY_EXT`. For JSON/YAML, the dispatcher content-sniffs — see the IAM/Sigma/control_framework routing |
| Change what Claude extracts | `prompts/extract_*.md` + the corresponding Pydantic schema in `app/schemas.py` |
| Add a chat tool | `app/kb/tools.py::TOOL_SCHEMAS` (Anthropic schema) + `execute_tool()` (local dispatch) |
| Add a new report | `app/claude/reports.py` (add to `REPORT_REGISTRY`), `prompts/report_<kind>.md`, Pydantic schema in `app/schemas.py`, router case in `app/routers/reports.py::generate_report` |
| Add a new nudge kind | `app/claude/nudges.py::generate_nudges()` (add a gate function), call `nudges_store.insert(kind=...)` |
| Add a SQL table | `app/db.py::_init_schema` (CREATE TABLE IF NOT EXISTS) + an additive migration in `_migrate_app_state_columns` if you're adding columns to an existing table |
| Change the home dashboard / top-nav | `app/routers/dashboard.py` — handles `/`, `/dashboard`, `/teams/*`, `/search`; the Org→Team→Project hierarchy lives here |
| Change the token usage / cost breakdown page | `app/routers/pages.py::usage_page` (`GET /usage`) + `usage_breakdown` (`GET /api/usage/breakdown`). Queries all three token tables (messages, reports, api_calls) and returns breakdowns by source, model, call site, and day. Template: `app/templates/usage.html`. The cost badge in the global header is a link to this page. |
| Change the D3 knowledge graph | `app/static/graph.js` (D3 v7 force simulation; `renderGraph(containerId, apiUrl, options)`) + `app/templates/knowledge_graph.html` (`/knowledge-graph` full-page route). The `GET /api/entities-graph?type=all` route calls `app/kb/relationships.py::graph_for_all_types()`. The legacy call shape `renderGraph("Service", 2)` is handled by a compat shim at the bottom of `graph.js`. |
| Add a versioned artifact (TM-style) | Mirror `app/storage/threat_models_store.py` (version per scope) + `app/claude/threat_modeling.py` (delta-aware regen with prior in prompt) |
| Author a workstream artifact | Mirror Phase 13: `<artifact>s_store.py` + `app/claude/<artifact>.py` (seed via Sonnet from freewrite) + `prompts/<artifact>_draft.md` + 2 templates (`<artifact>s.html` list, `<artifact>_<new\|detail>.html`) |
| Add a coverage / visibility analysis | Pattern in Phase 14: `app/kb/<kind>.py` for in-process queries + `app/claude/<analysis>.py` for Sonnet-driven synthesis + dedicated parser if the artifact is a new ingest type |
| Capture a lesson from an artifact | `app/claude/lesson_extractor.py::extract_from_<source>()` — runs synchronously on publish/reject; persisted to `lessons` table |
| Add ownership / personal-dashboard signal | `app/routers/me.py::_risk_score_for(entity_id)` — append to the heuristic mix |
| Change service ownership / on-call roster | `app/storage/ownership_store.py` (CRUD + `seed_from_graph`) + `app/routers/ownership.py` (`/ownership` page, `/api/ownership`). Table `service_ownership` (`_migrate_service_ownership` in `app/db.py`). Surfaced on Service `entity_detail.html`, the Today home ("Services you own"), the `get_service_ownership` chat tool, IR-runbook escalation (`ir_runbook.py::_build_context`), and the `ownership_gap` nudge. Distinct from `owned_store` (the user's *personal* RACI claims). |
| Change the front door / Today home | `/` is served by `app/routers/pages.py::home` → `index.html` (personal "Today" companion). `/dashboard` (`dashboard.py`) is the org→team→project "Workspaces" console — do NOT re-add a `/` → `/dashboard` redirect. Daily-companion pages live under the "Daily" nav group in `base.html`: `/journal`, `/followups`, `/cadence`, `/meeting-prep`, `/notes`. |
| Add a continuous-ingestion connector | `app/ingest/watchers/<kind>.py` implementing `scan(watcher_row) -> ScanResult` + register in `watchers/__init__.py::dispatch`. Kinds: `folder`, `ics_url`, `cve_feed`, `github_repo`. Users enable via Settings → Integrations. |
| Modify the two prompt-cache breakpoints | `app/claude/caching.py` — `build_system_block(role_mode, lens)` (system prompt, 1h TTL), `build_kb_block(hits, entity_cards)` (per-turn retrieved context, 5m TTL), `build_scope_block(service_id=None)` (canonical KB-scope, 1h TTL, shared across reports + anniversaries + day1 + plan + meeting prep + policy + compliance wizard). Use the `CACHE_5M` / `CACHE_1H` constants from the same module instead of inlining the dict. |
| Add a batched background job (50% off) | `app/claude/batches.py` — declare a handler with `@batches.register("<kind>")` (and optionally `@batches.register_finalizer("<kind>")` for N→1 aggregation patterns). Build each request via `app/claude/batch_helpers.py::tool_params_for(cls)` (Pydantic-class JSON schema as the forced tool's `input_schema`) and `extract_validated(msg, cls)` in the handler. Submit via `batches.submit(kind, requests, payload)`; scheduler `_tick` polls every minute. The synchronous `messages.parse` path stays for HTTP / user-waiting call sites. |
| Change smart auto-categorization rules | `app/ingest/auto_categorize.py` — `suggest_category(path)` (path-keyword + content-sniff heuristics) and `walk_directory(root)` (returns `(path, category)` pairs, skipping hidden/.git/node_modules). `PARSEABLE_EXTS` controls which extensions `walk_directory` includes (currently includes `.mmd`). Mirrors heuristics in `app/templates/ingest.html` JS (`guessCategory`). |
| Add or switch projects | `app/storage/projects_store.py` + `app/routers/projects.py`. `project_id TEXT` FK added to 7 tables (documents, chunks, entities, relationships, reports, conversations, messages). Active project set in `app_state`; the project switcher in the topnav reads it from `/api/projects`. Projects belong to Teams (`team_id`); Teams belong to an Org (`org_id`). The full 3-level hierarchy (Org→Team→Project) is navigated via `app/routers/dashboard.py`. |
| Change the side-panel chat UI | `app/templates/base.html` — the entire panel markup + ~180-line JS IIFE lives at the bottom of the `<script>` block. Panel is suppressed on `/chat` and `/onboarding` via `SUPPRESS_PATHS`. Width (240–600px), open/closed state, and `panelConvId` persist in `localStorage`. `--topbar-h` and `--footer-h` are set at runtime so the panel height fits exactly between them. CSS in `app/static/style.css` under `/* ── Side panel layout ──`. |
| Add/modify IR runbooks | `app/claude/ir_runbook.py::generate(service_id, threat_scenario, severity)` → `app/storage/ir_runbooks_store.py` → `app/routers/ir_runbooks.py`; prompt in `prompts/ir_runbook.md`. Runbook is KB-contextual (pulls service TM, postmortems, IAM). |
| Add/modify policy generation | `app/claude/policy_generator.py` — 5 kinds: `acceptable_use`, `incident_response`, `secure_sdl`, `vulnerability_management`, `data_classification`. Mirrors the `reports.py` pattern; prompts in `prompts/policy_<kind>.md`. Router: `app/routers/policies.py`. |
| Add/modify risk register | `app/storage/risks_store.py` + `app/claude/risk_register.py::assess(risk_id)` (Sonnet-driven assessment). Vulnerability intake queue at `app/storage/vulnerabilities_store.py`; promote-to-risk via `promote_to_risk()`. Router: `app/routers/risks.py` + `app/routers/vulnerabilities.py`. |
| Change security program metrics | `app/routers/security_program.py::_collect_metrics()` — aggregates counts from all major tables into `SecurityProgramMetrics`. `take_snapshot()` persists to `security_program_snapshots`. Exec brief via `POST /api/security-program/executive-brief`. |
| Change the intake interview | `app/routers/intake.py` (questions + complete flow) + `app/claude/intake_seeder.py::seed_from_answers()` (creates entity stubs with `provenance='user'`, `stub_source='intake_interview'`). State persists in `intake_interview` table. |
| Modify the discovery flow | `app/routers/discovery.py` — GitHub org scan (`POST /api/discovery/github-scan`) and team/people CSV import (`POST /api/discovery/team-import`). Both feed the entity graph. |
| Add/modify 90-day plan | `app/claude/plan_generator.py::generate()` + `app/storage/plan_store.py` (`ninety_day_plan` table). Router: `app/routers/plan.py`. |
| Change the Org→Team hierarchy | `app/storage/{organizations,teams}_store.py` + `app/routers/teams.py`. Projects belong to Teams; Teams belong to an Org. Routes: `/teams/{team_id}`, `/teams/{team_id}/projects/{project_id}`. `app/routers/dashboard.py` handles all hierarchy rendering. |

## Living artifacts pattern (Phase 12+)

Tank's later phases shifted from "one-shot reports" to **living
artifacts** — versioned documents (threat models, decisions, design
reviews, postmortems) Tank hosts and re-generates as the KB changes.
The pattern, common across these phases:

1. Schema: dedicated table with a status / version field.
2. Storage: store module with the standard `create/get/list_*` shape,
   writes under `LOCK`.
3. Claude helper: Sonnet-driven seed/draft/generate with the artifact's
   freewrite as input + (for versioned artifacts) the prior version
   in the prompt for delta-aware regeneration.
4. Router: REST API + server-rendered pages.
5. Two templates: list + detail/editor.
6. Hooks into other systems: spawn followups, spawn decisions,
   surface in nudges, expose to chat via `app/kb/tools.py`.
7. Drift detection (where relevant): a hash over contributing chunks
   that the regen path compares to current.

Look at `app/claude/threat_modeling.py` for the reference
implementation.

## The three big subsystems (continued — Phase 12+ additions)

**4. Living threat models + decisions log** (`app/claude/threat_modeling.py`,
`app/claude/decisions.py`, `app/storage/{threat_models,decisions}_store.py`,
`app/routers/{threat_models,decisions}.py`).

`threat_models` is a per-service, versioned table. Generating bumps
the version; `arch_snapshot_hash` (sha256 over contributing chunks)
drives `find_drift()`. The regen prompt receives the prior TM and asks
Sonnet to mark each prior threat `still_valid | invalidated | updated`
plus add genuinely `new` threats. The decisions log tracks deliberate
choices with `kind ∈ {design_choice, accepted_risk, deferred_fix,
security_invariant}`; the `expires_at` field drives the
`decision_expiring` nudge.

**5. Security workstreams** (`app/claude/{design_review,postmortem_authoring,
tabletop}.py`, `app/storage/{design_reviews,postmortems,tabletops}_store.py`,
`app/routers/{design_reviews,postmortems,tabletops}.py`).

Three mini-apps: design-review intake → checklist → approval (spawns
decisions); postmortem authoring from freewrite (action items become
followups on publish, lessons get extracted); tabletop scenario
generator with timed injects and lessons capture. The nightly 22:00
scheduler tick auto-generates `meeting_prep` briefs for tomorrow's
ICS-imported meetings (rate-limited to 5/day).

**6. Coverage + visibility** (`app/kb/{detections,iam,compliance}.py`,
`app/claude/{attack_mapping,attack_surface,iam_translator,compliance}.py`).

New parsers (`app/ingest/parsers/{sigma,iam,control_framework}.py`)
bring in detection rules, IAM policies, and control frameworks as
first-class ingest types. The `parsers/__init__.py::dispatch` is now
content-sniffing for JSON/YAML — same extension, different routes
based on the body. Sonnet-driven analyses produce `attack_mapping`
and `iam_audit` reports. Weekly Sunday 09:00 attack-surface snapshot
diffs against the prior week.

**7. Continuous learning + memory** (`app/claude/{lesson_extractor,
glossary_extractor,philosophy,anniversary_security}.py`,
`app/storage/{lessons,glossary,owned}_store.py`, `app/routers/{lessons,
glossary,me,philosophy}.py`).

Postmortems and rejected design reviews auto-extract lessons; the
lessons DB is search/tag-indexed. The glossary builder proposes
company-specific jargon for user confirmation. `app_state.philosophy_doc_id`
points to a curated security-philosophy `reports` row seeded at
Day-30 and evolved at Day-60/90/180/365. `/me` is the personal
ownership dashboard — users claim Service entities; the heuristic
risk score weighs TM drift, unaddressed threats, expired decisions,
and open postmortem action items.

**8. Risk register + vulnerability triage** (`app/claude/risk_register.py`,
`app/storage/{risks,vulnerabilities}_store.py`,
`app/routers/{risks,vulnerabilities}.py`).

`risks` table holds assessed risks with `likelihood`, `impact`,
`composite_score`, and `review_due_at`. `assess(risk_id)` calls Sonnet
with KB context to fill those fields. `vulnerabilities` is an intake
queue: `create → triage (set severity/notes) → assign (owner + due) →
close (patched/accepted/wont_fix) | promote_to_risk()`. The
`risk_register` report in `REPORT_REGISTRY` renders the full register as
a markdown table.

**9. First-hire onboarding suite** (`app/routers/{intake,discovery,
stack_audit,plan}.py`, `app/claude/{intake_seeder,plan_generator}.py`,
`app/storage/{intake,plan,asset_inventory}_store.py`).

Four sequential steps surfaced in `/onboarding`:
1. **Intake interview** — structured Q&A seeds entity stubs (`provenance='user'`,
   `stub_source='intake_interview'`, confidence 0.3) and populates
   `app_state` (role, tenure start, team, company).
2. **Discovery** — GitHub org scan + team/people CSV import feed the entity
   graph without full-document ingest.
3. **Stack audit** — user categorizes discovered services via a drag-and-drop
   matrix; categories persist in `asset_inventory`.
4. **90-day plan** — `plan_generator.generate()` produces a phased task
   list seeded from intake answers + KB, stored in `ninety_day_plan`.

**10. Security program dashboard** (`app/routers/security_program.py`,
`app/storage/` via direct DB queries, `prompts/executive_security_brief.md`).

`_collect_metrics()` aggregates counts from all major tables into
`SecurityProgramMetrics` (open risks, vuln age, TM drift, compliance
coverage, nudge counts, etc.). `take_snapshot()` snapshots these into
`security_program_snapshots` (diffs surfaced in the UI). The Sunday 09:30
scheduler job fires automatically. `POST /api/security-program/executive-brief`
generates a Sonnet-written exec brief rehydrated for display.

**11. Policy generator** (`app/claude/policy_generator.py`,
`app/storage/policies_store.py`, `app/routers/policies.py`).

Five policy kinds: `acceptable_use`, `incident_response`, `secure_sdl`,
`vulnerability_management`, `data_classification`. Each calls Sonnet with
the org's KB context (entity graph + role profile). Prompts in
`prompts/policy_<kind>.md`. The result is stored in `policy_artifact`
and rendered as markdown in `/policies/<kind>`. Mirrors the `reports.py`
pattern — reuse `_build_scope_block()` idiom for KB injection.

## Token cost tracking (three tables)

`/api/usage/cost` (simple total) and `/api/usage/breakdown` (full breakdown) aggregate from all three sources:

1. **`messages`** — chat turns; all 4 token fields (`tokens_in`, `tokens_out`, `cache_read_in`, `cache_create_in`).
2. **`reports`** — generated reports; `cache_read_in`/`cache_create_in` columns added by `_migrate_reports_cache_columns` in `app/db.py`.
3. **`api_calls`** — every other Claude call; `app/storage/api_calls_store.py::record()` is the writer.

`app/config.py::log_token_usage(call_site, model, usage)` is the single function every Claude call must invoke after getting a response. It writes to `api_calls` and, when `TANK_DEBUG_TOKENS=1`, logs per-call counts to the console. If a new module makes a Claude call without calling `log_token_usage()`, that spend is invisible to the cost counter.

`reports_store.insert()` additionally takes `cache_read_in` / `cache_create_in` — pass them or the reports table will undercount cache savings.

The **`/usage`** page (`app/routers/pages.py::usage_page` + `app/templates/usage.html`) renders the breakdown by source, model, call site, and last-14-days timeline. The global header cost badge (`$—`) is a link to this page. `GET /api/usage/breakdown` is the JSON endpoint it consumes.

## Prompt-cache TTL helpers

`app/claude/caching.py` exposes two cache-control constants:

- `CACHE_5M` — default 5-minute ephemeral. Use for blocks that vary turn-to-turn (e.g. the KB hit set in `build_kb_block`, where the retrieved chunks depend on the query).
- `CACHE_1H` — 1-hour extended ephemeral. Use for blocks stable across a working session: role/lens system prompt (`build_system_block`), KB entity scope (`build_scope_block`), per-report system prompts, threat-model prior-version blocks, `policy_base` rules. Pays back across digest-time bursts and multi-policy/multi-risk sessions.

`build_scope_block(service_id=None)` is the canonical KB-scope helper used by reports, anniversaries, day-1 brief, plan generator, prioritization, meeting prep, policy generator, and compliance wizard. Lives in `app/claude/caching.py`; `app/claude/reports.py` keeps a thin `_build_scope_block` re-export for back-compat with existing imports.

## Anthropic Message Batches (50% off, async)

`app/claude/batches.py` wraps `client.messages.batches.create` for non-interactive scheduler fan-out. Submitted batches land in the `batch_jobs` table (`_migrate_batch_jobs` in `app/db.py`); the scheduler `_tick` calls `poll_inflight()` every ~60s and dispatches results to a kind-specific handler registered via `@batches.register("<kind>")`. Aggregator patterns (N→1) use `@batches.register_finalizer("<kind>")` to run once after all per-result handlers have fired.

All four scheduler fan-out consumers are migrated:

- `_fire_auto_briefs` (kind `auto_brief`) — Haiku, one request per upcoming meeting. Handler in `app/claude/meeting_prep.py::_handle_auto_brief` persists each rehydrated brief into the new `meeting_briefs` table.
- `_run_due_subscriptions` (kind `report_subscription`) — Sonnet, one request per due subscription. Dispatch table `_BATCH_DISPATCH` in `app/claude/reports.py` covers 12 of 14 kinds; `attack_mapping` routes to its own batch path and `iam_audit` stays sync (no Claude call). Handler `_handle_report_subscription` mirrors `_finalize` exactly.
- `_maybe_anniversary` (kind `anniversary_bundle`) — one batch carrying 2–3 artifacts per tenure milestone (generic retro + security retro + philosophy seed/evolve). Handler dispatches by `custom_id` prefix to the right persistence path.
- `attack_mapping.schedule_batch` (kind `attack_mapping_per_tm`) — Sonnet, one request per latest Threat Model. Per-result handler writes partial rows to `attack_mapping_scratch`; finalizer aggregates, computes coverage_summary + top_gaps, persists ONE combined report under `kind="attack_mapping"`, then clears scratch.

Structured-output adapter: `app/claude/batch_helpers.py` provides `tool_params_for(cls)` and `extract_validated(msg, cls)`. The Batches endpoint doesn't accept `output_format=PydanticClass`, so each migration declares a single tool whose `input_schema` is the Pydantic class's JSON schema and forces it via `tool_choice={"type": "tool", "name": ...}`. The synchronous `messages.parse` path stays in place for interactive (user-waiting) call sites.

Token accounting for batch results uses `log_token_usage(f"batches.{kind}", model, usage)` inside the result loop — they show up as ordinary `api_calls` rows. Subscription reports additionally pass `tokens_in/out/cache_read_in/cache_create_in` to `reports_store.insert` so per-report spend is captured in the reports table (matches sync path).

## DFD Threat Modeling

Three-stage pipeline: Stage 1 (4-mode input) → Stage 2 (SSE progress) → Stage 3 (split-panel workspace). Key files:

- **`app/schemas.py`** — `DFDThreat` (renamed from old `STRIDEThreat` to fix naming collision with reports `STRIDEThreat`); added `threat_id`, `element_label`, `title`, `cvss_estimate: float | None`, `references: list[str]`; `DFDMermaidGeneration` schema for generate flows.
- **`app/claude/dfd_analyzer.py`** — `analyze_mermaid(src, force, project_id, project_notes, input_format)` → `(dfd_id, analysis, from_cache)`; `analyze_image(bytes, media_type, project_id, project_notes)` → same tuple; `generate_from_description(text, project_notes)` → `DFDMermaidGeneration`; `generate_from_document(file_bytes, filename, project_notes)` → `DFDMermaidGeneration`. Uses `pypdf`/`python-docx` for document text extraction.
- **`app/routers/dfd.py`** — `POST /api/dfd/generate-from-description` and `POST /api/dfd/generate-from-doc` (return `{mermaid, notes}`); `POST /api/dfd/start-analysis` (returns `{task_id}`); `POST /api/dfd/start-analysis-image` (image variant); `GET /api/dfd/task/{task_id}/stream` (SSE drain, reuses `event_bus.py` pattern); `GET /api/dfd/{id}/export?format=mmd|original_mmd|json`. Legacy `POST /api/dfd/analyze` retained for backward compat. `GET /dfd/from-kb/{doc_id}` bridge page auto-starts analysis from a KB-ingested document (image → start-analysis-image; text → generate-from-doc). `GET /api/dfd/kb-doc-bytes/{doc_id}` serves the raw file; falls back to DB-chunk reassembly if `source_path` is gone.
- **`app/storage/dfd_store.py`** — `insert()` accepts `input_format`, `project_id`, `cached`; `list_recent()` accepts optional `project_id` filter.
- **`app/db.py`** — `_migrate_dfd_columns()` adds `input_format TEXT`, `project_id TEXT`, `cached INTEGER NOT NULL DEFAULT 0` columns to `dfd_analyses` (idempotent via `_add_col_safe()`).
- **`prompts/dfd_stride.md`** — STRIDE analysis prompt; updated for new threat fields; Low severity color `#4F46E5` (was `#2563eb`); severity indicator on node labels (`⚠ H`); project context injection.
- **`prompts/dfd_generate_doc.md`** — new: generate Mermaid from architecture document.
- **`prompts/dfd_generate_desc.md`** — new: generate Mermaid from plain-language description.
- **`prompts/dfd_improve.md`** — diagram-completion prompt (unchanged).

**SSE progress pattern:** `POST /api/dfd/start-analysis` → `task_id`; background `asyncio.Task` emits step events to `f"dfd.{task_id}"` topic via `event_bus.publish()`; 4 steps (parsing → components → attack surfaces → threat model); `done` event carries `{dfd_id, cached}`.

**Severity colors (single source of truth):**
- CSS variables in `:root`: `--sev-critical: #DC2626`, `--sev-high: #EA580C`, `--sev-medium: #D97706`, `--sev-low: #4F46E5`
- JS constant `SEV_COLORS` in dfd templates mirrors these

**PDF export:** CSS `@media print` only — no jsPDF/html2canvas. Produces cover page, full-width diagram SVG, threat table, STRIDE coverage matrix (6×4), Mermaid appendix.

The `improve_mermaid` endpoint pulls KB context using `hybrid_search("data flow architecture services trust boundary", k=10)` and sends it alongside the diagram.

**`.mmd` ingest:** `.mmd` is registered in `parsers/__init__.py::_BY_EXT` (→ MarkdownParser) and in `auto_categorize.py::PARSEABLE_EXTS`. Users can ingest Mermaid source files via `/ingest` and then open them from the DFD "← Existing" tab's "From your knowledge base" section.

**DFD "← Existing" tab:** The tab appears when either `dfd_analyses` rows exist OR ingested documents are present. It shows two sections: analyzed DFDs (from `dfd_analyses`) and architecture/image KB documents (filtered from `documents` table). The router (`dfd_page`) filters `kb_docs` to `kind='image'`, `category='architecture'`, or path keyword matches (dfd/diagram/flow/architect).

**Mermaid SVG rendering:** Mermaid v10+ renders node labels inside `<foreignObject>` elements. Never pass `mermaid.render()` output through DOMPurify — `USE_PROFILES:{svg:true}` strips `<foreignObject>` and `<style>` blocks, making all text invisible. Use `element.innerHTML = result.svg` directly; Mermaid's own `securityLevel:'strict'` already sanitizes the output.

## Operations layer (the always-on-VM additions)

Tank is designed to run on a user-owned dev VM via SSH tunnel, not
on a laptop that sleeps. Key durable + operational pieces:

- **Healthcheck**: `GET /healthz` returns
  `{ok, scheduler, db, tenure_day}`. Wire into systemd / external
  probe. No Sonnet calls; cheap. Defined in `app/main.py`.
- **Durable scheduler state**: `scheduler_state` table replaces the
  previous in-memory `_LAST_FIRED` dict. Restarts (intentional or
  via `Restart=on-failure`) don't double-fire or skip today's jobs.
  See `app/storage/scheduler_state_store.py`.
- **TZ-aware scheduler**: `app/claude/scheduler.py::_now()` honors
  `TANK_TIMEZONE` (IANA name). Hosted VMs are usually UTC, which
  is almost never what the user wants for `digest_time = 08:00`.
  Other env vars: `TANK_DIGEST_TIME` (default `08:00`), `TANK_DB_PATH`
  (default `~/.tank/db.sqlite`), `TANK_ENV` (`dev` enables uvicorn
  `--reload`; `prod` disables it — systemd unit forces `prod`).
- **Weekly SQLite backup**: Sunday 03:00 job uses
  `sqlite3.Connection.backup()` (WAL-safe, online) to write
  `~/.tank/backups/db-YYYY-MM-DD.sqlite`. The `backup_log` table
  is the ledger; retention drops everything beyond the most recent 8.
- **Anthropic SDK retries**: `app/config.py::get_client()` sets
  `max_retries=4` (up from default 2) and an explicit 600s timeout.
  Both env-overridable via `TANK_API_MAX_RETRIES` and
  `TANK_API_TIMEOUT_SECONDS`.
- **Wipe phrase challenge**: `/api/wipe` requires
  `confirm_phrase="delete tank"` (case-sensitive) in the form body.
  Prevents accidental nukes from stale tabs. Backups in
  `~/.tank/backups/` are NOT touched by the wipe.
- **Event-bus fan-out**: `app/claude/event_bus.py` gives each SSE
  subscriber its own queue. When the last subscriber for a topic
  unsubscribes, the topic is removed from the registry — no
  unbounded growth across long uptimes. Multi-tab safe (both tabs
  receive every event).
- **systemd unit**: `scripts/tank.service` + `scripts/install-systemd.sh`.
  `Restart=on-failure` with burst-cap, 30s graceful shutdown,
  `NoNewPrivileges` + `ProtectSystem=strict` sandbox, `EnvironmentFile`
  reads `.env`. Forces `TANK_ENV=prod` regardless of `.env` to
  disable `--reload` under a supervisor.

## Theme + client-side state

Nyx-inspired theme in `app/static/style.css` — purple-tinted dark
default + light override via `html.theme-light` class. Toggle button
in the navbar (`app/templates/base.html`) sets `localStorage`
`tank-theme = "dark" | "light"`. A synchronous init script in
`<head>` reads the saved preference before body renders to prevent
flash. Loads Inter + JetBrains Mono from Google Fonts; falls back
gracefully if blocked.

Other `localStorage` keys used across the UI:

| Key | Purpose |
| --- | --- |
| `tank-theme` | `"dark"` \| `"light"` |
| `tank-panel-open` | `"true"` \| `"false"` — side panel open/closed |
| `tank-panel-width` | integer px (240–600) — side panel width |
| `tank-panel-conv` | conversation ID for the persistent side panel |
| `tank-hints-dismissed` | `"1"` — contextual hints popup on Today page |

## Hard rules

- **Two Claude models, strict split**: `MODEL = "claude-sonnet-4-6"` for
  all reasoning tasks (chat, reports, design reviews, postmortems,
  tabletops, threat models, DFD analysis, Day-1 brief, anniversaries,
  notes, vision). `HAIKU_MODEL = "claude-haiku-4-5-20251001"` for
  structured-extraction tasks with predictable JSON schemas (entity
  extraction in `extractor.py`, meeting prep, journal/lesson extraction,
  nudge question-of-week). **Haiku does not support extended thinking**
  — remove `thinking=...` from any call you switch to Haiku. Do not add
  further per-call overrides without a strong reason.
- **Pre-redact at ingest**, not at send time. Adding a code path that
  redacts at send time means it's possible to forget; the existing
  invariant is "if it's in `chunks.text_redacted`, it's already safe."
- **Tools return pre-redacted data.** A defense-in-depth
  `apply_redactions` runs on tool results before they go back to Claude
  in `app/claude/chat.py`. Don't bypass.
- **No raw source code to Claude.** Repos are ingested as a
  `code_facts.RepoSummary` (manifests, dockerfile, CI files, grep hits,
  README). Source files themselves are never in any prompt.
- **No remote embedding API.** Local sentence-transformers only — see
  `app/ingest/embedder.py`. Privacy beats retrieval quality.
- **Anthropic SDK call shape**: `messages.parse(model=MODEL,
  thinking={"type":"adaptive"}, system=[...], messages=[...],
  output_format=PydanticClass)` for interactive structured output;
  `messages.stream(...)` for chat; `messages.batches.create(requests=[...])`
  via `app/claude/batches.py` for scheduler fan-out (50% off, async,
  no `output_format` — use `tool_params_for` / `extract_validated`).
  Prompt caching via inline text blocks with `"cache_control": CACHE_5M`
  (per-turn) or `CACHE_1H` (stable for the session) from
  `app/claude/caching.py`.
- **SQLite**: single global connection guarded by `threading.Lock` (see
  `app/db.py`). All writes go inside `with LOCK:`. WAL mode + foreign
  keys on.

## Known environment quirks

- macOS system Python 3.9 lacks `enable_load_extension`, which disables
  `sqlite-vec`. The graceful fallback in `app/db.py::_load_extensions`
  + `app/kb/search.py` works (FTS5 keyword search still functions); to
  get vector search, install Python from Homebrew or python.org.
- Python 3.9 also can't install recent `spacy` (needs ≥3.10). Person-
  name redaction (`app/redact/secrets.py::PERSON_RULE`) is off by
  default and gated by `TANK_ENABLE_PERSON_REDACTION=1`.
- Pydantic 2's `X | Y` syntax on 3.9 requires `eval_type_backport`
  (already in requirements). Don't replace with `Optional[X]` —
  consistent style across the file matters more than 3.9 friendliness.

## Reference patterns

This project mirrors patterns from `/Users/manuel.del.rio/projects/job-fit/`:
- `app/config.py`: env via `python-dotenv`, `@lru_cache get_client()`,
  `MODEL` constant, `load_prompt(name)`.
- `app/db.py`: module-level `_CONN` + `threading.Lock` + WAL + per-table
  store modules.
- Prompts as `.md` files in `prompts/`, loaded by name; never inlined.

When in doubt about an idiom, check how job-fit does it.
