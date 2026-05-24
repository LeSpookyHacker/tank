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

- Chat with 13 tools over the KB.
- 10 report kinds (threat landscape, cross-service gaps, 30/60/90,
  stakeholder map, questions-for-team, control matrix, on-call
  handoff, weekly security digest, ATT&CK mapping, IAM audit).
- Living artifacts: versioned threat models (drift-aware), decisions
  log, design reviews, postmortems, tabletops.
- Partner mode: Day-1 brief, journal, follow-ups, recurring reports,
  anniversary retros (generic + security-focused), philosophy doc.
- Second brain: lessons-learned DB, glossary, ownership dashboard,
  tenure-aware lens (map / prioritize / execute / maintain).

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

- Daily digest at `app_state.digest_time` → regenerate nudges (8 kinds,
  rate-limited to 2/day), run due `report_subscriptions`, anniversary
  check at days 30/60/90/180/365.
- Friday 16:00 → weekly reflection trigger.
- Weekday 18:00 → journal-prompt nudge if no entry today.

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
| Change the home dashboard | `app/routers/pages.py` (data) + `app/templates/index.html` (render) |
| Add a versioned artifact (TM-style) | Mirror `app/storage/threat_models_store.py` (version per scope) + `app/claude/threat_modeling.py` (delta-aware regen with prior in prompt) |
| Author a workstream artifact | Mirror Phase 13: `<artifact>s_store.py` + `app/claude/<artifact>.py` (seed via Sonnet from freewrite) + `prompts/<artifact>_draft.md` + 2 templates (`<artifact>s.html` list, `<artifact>_<new\|detail>.html`) |
| Add a coverage / visibility analysis | Pattern in Phase 14: `app/kb/<kind>.py` for in-process queries + `app/claude/<analysis>.py` for Sonnet-driven synthesis + dedicated parser if the artifact is a new ingest type |
| Capture a lesson from an artifact | `app/claude/lesson_extractor.py::extract_from_<source>()` — runs synchronously on publish/reject; persisted to `lessons` table |
| Add ownership / personal-dashboard signal | `app/routers/me.py::_risk_score_for(entity_id)` — append to the heuristic mix |
| Add a continuous-ingestion connector | `app/ingest/watchers/<kind>.py` implementing `scan(watcher_row) -> ScanResult` + register in `watchers/__init__.py::dispatch`. Kinds: `folder`, `ics_url`, `cve_feed`, `github_repo`. Users enable via Settings → Integrations. |
| Modify the two prompt-cache breakpoints | `app/claude/caching.py` — `build_system_block(role_mode, lens)` (system prompt) and `build_kb_block(hits, entity_cards)` (retrieved context). Both return `{"cache_control": {"type": "ephemeral"}}` blocks. |

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

## Theme

Nyx-inspired theme in `app/static/style.css` — purple-tinted dark
default + light override via `html.theme-light` class. Toggle button
in the navbar (`app/templates/base.html`) sets `localStorage`
`tank-theme = "dark" | "light"`. A synchronous init script in
`<head>` reads the saved preference before body renders to prevent
flash. Loads Inter + JetBrains Mono from Google Fonts; falls back
gracefully if blocked.

## Hard rules

- **Single Claude model**: `MODEL = "claude-sonnet-4-6"` in
  `app/config.py`. Used for ingest extraction, chat, every report,
  vision (diagrams), nudges, notes, Day-1 brief, anniversaries. There
  is no Opus tier. Don't add per-call model overrides without a strong
  reason — uniform model means uniform prompt-cache behavior.
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
  output_format=PydanticClass)` for structured output;
  `messages.stream(...)` for chat. Prompt caching via inline
  `{"type":"text","text":"...","cache_control":{"type":"ephemeral"}}`.
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
