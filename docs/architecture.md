# Architecture

A deep-dive on Tank's internals — the three big subsystems, the
privacy contract that gates every data flow, and the data model.

For an at-a-glance overview, the top-level [README.md](../README.md)
has a 20-line ASCII block diagram.

---

## The privacy contract drives every data flow

```
parse → CHUNKER → REDACT  →  SQLite                  →  Anthropic API
                                  ↓ retrieve              ↑ (redacted)
                              cached KB block             rehydrate locally
                                  ↓
                              prompt assembly
```

### One chokepoint: `apply_redactions`

[app/redact/engine.py](../app/redact/engine.py) defines
`apply_redactions(text)`. Every byte that reaches the Claude API has
passed through it. Chunks are pre-redacted at **ingest** time (not
at send time) — `chunks.text_redacted` is what flows out;
`chunks.text_original` is local-only forensics.

> If you add a new code path that calls Claude, run user text
> through `apply_redactions` first and rehydrate the response with
> `rehydrate(text, load_rehydration_map(used_placeholders))`.

### Defense-in-depth improvements (security audit 2026-05-27)

The privacy contract was tightened in a focused hardening pass:

- **Rehydration is now scoped to the outgoing prompt.** Chat rehydration
  only substitutes placeholders that appeared in the prompt Claude
  actually received. A prompt-injection attack cannot force Tank to
  rehydrate arbitrary `redaction_map` entries that were never in scope.
- **All user-supplied text fields pass through `apply_redactions`.**
  Previously the main freewrite body was redacted but secondary fields
  (project notes, artifact titles, tabletop scenario hooks) were not.
  Every field injected into a Claude prompt now goes through the engine.
- **Security headers on every response.** `SecurityHeadersMiddleware`
  in `app/main.py` sets `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and a
  `Content-Security-Policy` on all responses.
- **Upload hardening.** File uploads are limited to 100 MB;
  filenames are sanitized with `os.path.basename()` + `.lstrip(".")[:200]`;
  the path-ingest endpoint is restricted to the user's home directory subtree.
- **ICS SSRF protection.** The calendar watcher validates URLs before
  fetching — blocks RFC1918 / loopback / link-local IPs, the cloud
  metadata endpoint (`169.254.169.254`, `metadata.google.internal`),
  and non-http/https schemes.

### Determinism

`key = sha256(category + ":" + lower(strip(match)))`. The same email
becomes the same `[EMAIL_007]` placeholder forever, across every
document. This is what makes the redacted KB still queryable — "the
person at `[EMAIL_007]`" recurs across many chunks and Sonnet can
reason about them as one entity.

### Secrets are one-way

For `category='secret_token'`, `redaction_map.original_text` is
overwritten with `sha256(original)` at insert time. **Secrets cannot
be rehydrated, even internally.** This is intentional — defense in
depth. You look up the actual secret in the source doc yourself.

### Categories

| Category | Detection | Default | Rehydratable |
| --- | --- | --- | --- |
| `email` | RFC-ish regex | on | yes |
| `internal_hostname` | `*.<your_tld>`, `*.internal`, `*.corp`, `*.local`, `*.lan`, `*.intra` | on | yes |
| `public_hostname` | other FQDNs | off | yes |
| `ipv4_private` | RFC1918 + loopback + link-local + CGNAT + ULA | on | yes |
| `ipv4_public` | other IPs | off | yes |
| `aws_account_id` | 12-digit near AWS context | on | yes |
| `aws_arn` | full ARN regex (preserves service, redacts acct+resource) | on | yes |
| `gcp_project` | project-id near GCP context | on | yes |
| `azure_subscription` | UUID near subscription/tenant | on | yes |
| `secret_token` | `detect-secrets` plugins + Shannon entropy ≥4.5 on b64/hex tokens ≥20 chars | **on, non-disableable** | **no — one-way hash** |
| `person_name` | spaCy NER + ingested-person wordlist | off (Py 3.10+) | yes |
| `custom:<name>` | user-supplied regex from `redaction_rules` table | configurable | yes |

> ⬜ **Screenshot placeholder**: settings page showing the redaction
> categories with toggles + per-category match counts.
>
> ![Redaction settings](images/arch-redaction-settings.png)

### Audit surfaces

- `GET /api/redaction/map?category=...` — list placeholders +
  categories + occurrence counts. Originals never returned over HTTP.
- Settings → recent redactions — last 200 with "this was fine →
  allowlist exception" affordance.
- `messages.redacted_view` — stores exactly what Claude saw.
- `scripts/verify_privacy.py --fixture-pack` — grep the DB for
  any planted identifier in a redacted-view column. Exits non-zero
  on a hit.

---

## The three big subsystems

### Model selection

Tank uses two Claude models with a strict split:

| Model | Constant | Used for |
| --- | --- | --- |
| `claude-sonnet-4-6` | `MODEL` | Chat, reports, DFD analysis, threat models, design reviews, postmortems, tabletops, Day-1 brief, anniversaries, notes, vision (images) |
| `claude-haiku-4-5-20251001` | `HAIKU_MODEL` | Entity extraction, meeting prep, journal/lesson extraction, nudge question-of-week — structured JSON output with known schemas, no reasoning required |

Haiku does not support extended thinking — remove `thinking=...` from any call switched to Haiku.

### Token cost tracking

`/api/usage/cost` aggregates from three tables:

1. **`messages`** — chat turns (all 4 fields: in/out/cache_read/cache_create)
2. **`reports`** — generated reports (`cache_read_in`/`cache_create_in` columns)
3. **`api_calls`** — all other Claude calls; every module calls
   `config.log_token_usage(call_site, model, usage)` after each response.
   Batch results log as `batches.<kind>` rows here too.

Set `TANK_DEBUG_TOKENS=1` to log per-call counts to the console.

### Prompt-cache TTLs

`app/claude/caching.py` exposes two `cache_control` constants and a
canonical scope helper:

| Helper | TTL | What it caches |
| --- | --- | --- |
| `CACHE_5M` | 5 min ephemeral | Per-turn KB hit block (search results vary by query, so a longer TTL doesn't help) |
| `CACHE_1H` | 1 h extended ephemeral | System prompts + role/lens + KB entity scope + threat-model prior version + `policy_base` rules — anything stable across a working session |
| `build_scope_block(service_id=None)` | uses `CACHE_1H` | Single shared block fed to reports, anniversaries, day-1 brief, plan generator, meeting prep, policy generator, compliance wizard. Digest-time bursts that run multiple reports share this cache. |

`build_system_block(role_mode, lens)` and `build_kb_block(hits, cards)`
are the chat-specific helpers. The KB block is intentionally `CACHE_5M`
because the hit set is per-query; everything else uses `CACHE_1H`.

---

### 1. Ingest pipeline (`app/ingest/`)

`pipeline.py::ingest(path, category)` runs:

```
parse → chunk (RecursiveCharacterTextSplitter + tiktoken, 800/120)
      → redact
      → bulk_insert_chunks + FTS5 + sqlite-vec write
      → entity extraction via Haiku messages.parse
      → entity/relationship upsert
```

Repos go through `ingest_repo()` → `code_facts.summarize()` — no
raw source ever sent; only the structured summary + README. The
summary collects: language LOC, dependency manifests, Dockerfile
facts, CI files, auth/secrets grep hits, CODEOWNERS, README,
ARCHITECTURE.md.

Parsers dispatch by extension (and for JSON/YAML, by content
sniffing) in `app/ingest/parsers/__init__.py`:

| Extension | Parser | Notes |
| --- | --- | --- |
| `.md` / `.markdown` / `.txt` | markdown.py | Section path from heading breadcrumb |
| `.pdf` | pdf.py | Per-page; low-text pages route to vision |
| `.docx` | docx.py | Heading styles → section path; tables → TSV |
| `.csv` | csv_json.py | Row batching (25/call) for CMDB shapes |
| `.json` / `.yaml` / `.yml` | content-sniff → iam / control_framework / csv_json / sigma | Same suffix, different routes by body |
| `.png` / `.jpg` / `.jpeg` / `.webp` / `.gif` | image.py | Sonnet vision via `extract_arch_diagram.md` |

The image parser calls Sonnet vision and stashes the structured
extraction in `meta["vision"]`; the extractor module picks it up
and persists entities/edges without re-prompting.

### 2. Chat with SSE + tool use (`app/claude/chat.py`, `app/routers/chat.py`)

This subsystem pioneers both streaming and tool use in Tank's stack.

`run_turn(conv_id, user_text)` is an async function that:

1. Redacts the user message.
2. Embeds locally (`sentence-transformers/all-MiniLM-L6-v2`).
3. Hybrid retrieves (sqlite-vec + FTS5 + reciprocal rank fusion in
   [app/kb/search.py](../app/kb/search.py)).
4. Pulls entity cards for top entities cited.
5. Builds `messages.stream(...)` with cached system + cached KB
   block + history.
6. Stream-loops: text deltas → SSE events; `tool_use` blocks →
   `app/kb/tools.py::execute_tool(name, args)` → tool_result →
   continue until `end_turn`.
7. Rehydrates the assistant text, persists `redacted_view` (audit)
   and `display_view` (UI).

**HTTP shape**: `POST /api/conversations/{id}/messages` kicks off an
asyncio.Task that drains events into a per-conversation queue.
The browser's `EventSource` subscribes via `GET .../stream`.
Reconnect-safe; multi-tab safe (per-subscriber queues).

**Synchronous SDK bridge**: the Anthropic SDK streaming context
manager is sync, so the chat loop runs it via
`loop.run_in_executor(None, _run_stream)`. Events bridge to asyncio
via [app/claude/event_bus.py](../app/claude/event_bus.py).

### 3. Reports + artifacts (`app/claude/reports.py` + Phase 12-15 modules)

Fourteen report kinds in `REPORT_REGISTRY`, sharing a cached scope
block built by `app/claude/caching.py::build_scope_block` (with a
thin `_build_scope_block` re-export in `reports.py` for back-compat).
Running multiple reports against the same global scope reuses the
1h-TTL prompt cache, so a digest tick that fires several subscriptions
back-to-back pays cache-read rates after the first.

Each report: `messages.parse(output_format=PydanticClass)` → render
Markdown → persist both redacted (audit) and rehydrated (display) in
the `reports` table.

| Kind | Phase | What it produces |
| --- | --- | --- |
| `threat_landscape` | 7 | STRIDE-style threat list for a service (one-shot, superseded by Phase-12 versioned TMs) |
| `cross_service_gaps` | 7 | Patterns spanning multiple services |
| `plan_30_60_90` | 7 | Trust-building / coalition / execute ladder |
| `stakeholder_map` | 7 | Tiered relationship map |
| `questions_for_team` | 7 | Ranked questions for a team or person |
| `control_matrix` | 7 | Service × control coverage table |
| `oncall_handoff` | 13 | Per-service handoff brief |
| `weekly_security_digest` | 13 | Mon-AM week-over-week summary |
| `attack_mapping` | 14 | Threats × ATT&CK technique × detection coverage |
| `iam_audit` | 14 | Ranked IAMPolicy risk audit |
| `risk_register` | 14 | Full register as a markdown table, ranked by residual score |
| `state_of_security` | 7+ | Monthly exec brief |
| `initial_assessment` | 7+ | 30-day Day-N findings report |
| `program_roadmap` | 7+ | 12-month roadmap from current trajectory |

Each kind that calls `messages.parse` also has a row in
`_BATCH_DISPATCH` (in `reports.py`) so the scheduler can submit due
subscriptions through the Batches API at 50% off — see the **Message
Batches** subsystem below. The synchronous path stays in place for
the HTTP route `POST /api/reports/{kind}` where the caller is waiting.

Beyond the report registry, **versioned artifacts** live in their
own tables:

- `threat_models` (per-service, versioned, drift-aware — Phase 12)
- `decisions` (design choices, accepted risks, deferred fixes,
  invariants — Phase 12)
- `design_reviews` (intake → checklist → approval — Phase 13)
- `postmortems_drafts` (authored from freewrite — Phase 13)
- `tabletops` (scenario + injects + lessons — Phase 13)
- `lessons` (auto-populated from postmortems, tabletops, DRs — Phase 15)

---

## Partner mode (daily-companion machinery)

Lives across `app/claude/{nudges, meeting_prep, notes, day1_brief,
anniversary, anniversary_security, journal_extractor, philosophy,
scheduler}.py` and `app/storage/{journal, kanban, followups, subscriptions,
usage, nudges, notes, glossary, lessons, owned, …}_store.py`.

The **Kanban board generator** (`app/routers/kanban.py`) serves `/kanban`
(board landing) and `/kanban/boards/{id}` (board view). Storage in
`app/storage/kanban_store.py` (`kanban_boards` + `kanban_cards` tables,
migrated via `app/db.py::_migrate_kanban`). The old `followups` table and
`/api/followups` endpoints remain for programmatic creation from postmortems
and dashboard widgets; kanban is the user-facing interface.

### The scheduler

A single `asyncio.Task` started in `app/main.py::lifespan` and
cancelled on shutdown. Wakes every 60s and dispatches:

| Trigger | Job | Notes |
| --- | --- | --- |
| `app_state.digest_time` daily | nudge regen (8 kinds, rate-limited to 2/day), due `report_subscriptions` run, anniversary check at days 30/60/90/180/365 | Subscriptions submit one `report_subscription` batch (12 of 14 kinds). Anniversary submits one `anniversary_bundle` batch carrying generic + security retros + philosophy seed/evolve. |
| `reflection_day` 16:00 | Weekly reflection trigger | UI-driven from here |
| Weekday 18:00 | Journal-prompt nudge | Only if no entry today |
| Daily 22:00 | Auto pre-meeting briefs | Up to 5 submitted as one `auto_brief` batch; rehydrated briefs persist to `meeting_briefs` when the batch lands |
| Sunday 09:00 | Attack-surface snapshot | Diffs against prior week (no Claude call) |
| Sunday 03:00 | SQLite backup | Retention: 8 most recent |
| Every tick (~60s) | `batches.poll_inflight` | Refreshes status of every in-flight Anthropic batch; dispatches finished results to the registered handler |

Last-fired markers are persisted to the `scheduler_state` table.
Restarts (intentional or `Restart=on-failure`) no longer double-fire
or skip same-day jobs. Set `TANK_TIMEZONE` if your VM's `localtime`
isn't yours.

### Anthropic Message Batches (50% off)

`app/claude/batches.py` wraps `client.messages.batches.create`. Each
fan-out workload above submits one batch per tick; results land
asynchronously and are processed by a kind-specific handler registered
via `@batches.register("<kind>")`. Aggregator patterns (one combined
report from N per-TM responses, as in `attack_mapping`) use
`@batches.register_finalizer("<kind>")` to run once after all
per-result handlers fire.

The Batches endpoint doesn't accept `output_format=PydanticClass`, so
each consumer module uses the structured-output adapter in
`app/claude/batch_helpers.py`:

- `tool_params_for(cls)` builds `(tools, tool_choice)` to force a
  single tool call whose `input_schema` is `cls.model_json_schema()`.
- `extract_validated(msg, cls)` walks the response for the `tool_use`
  block and validates its `.input` against the class.

In-flight batches live in the `batch_jobs` table (`id`, `anthropic_id`,
`kind`, `status`, `payload_json`, `result_summary`). The
`attack_mapping` aggregator additionally uses a short-lived
`attack_mapping_scratch` table to buffer per-TM rows between the
per-result handler and the finalizer.

The synchronous `messages.parse` path stays in place for every HTTP
route where the caller is waiting — `POST /api/reports/{kind}`,
`POST /api/meeting-prep`, the `attack_mapping` HTTP path, etc.

### The tenure lens

[app/role.py::current_lens()](../app/role.py) returns `map` |
`prioritize` | `execute` | `maintain` based on
`app_state.tenure_started_at`:

| Days since onboarding | Lens | Framing |
| --- | --- | --- |
| 1-14 | `map` | Coverage, who-owns-what, who-to-meet, fast wins |
| 15-60 | `prioritize` | Risk ranking, gap closure, control coverage |
| 61-180 | `execute` | Ongoing initiatives, decision logs, recurring patterns |
| 180+ | `maintain` | Drift, freshness, succession, "this TM is 14 months old" |

Chat system prompts load `prompts/chat_lens_<lens>.md` at runtime
and inject it into the system block. **Same KB, different lens.**

---

## Data model

Schema in [app/db.py](../app/db.py) — single `_init_schema` runs
all `CREATE TABLE IF NOT EXISTS` on first connection, plus an
additive `_migrate_app_state_columns` for the columns added in
later phases.

```
Foundation tables (Phase 1-2):
  documents, chunks, chunks_fts, chunks_vec
  entities, entity_chunks, relationships
  redaction_map, redaction_rules
  conversations, messages
  reports
  nudges, notes
  app_state

Daily-use additions (Phase 8):
  journal_entries, followups, kanban_boards, kanban_cards,
  report_subscriptions, usage_events, watchers, meetings

Living artifacts (Phase 12):
  threat_models, decisions

Workstreams (Phase 13):
  design_reviews, postmortems_drafts, tabletops

Coverage + visibility (Phase 14):
  attack_surface_snapshots, compliance_evidence

Second brain (Phase 15):
  lessons, glossary, owned_entities

Ops layer:
  scheduler_state         (durable last-fired markers)
  backup_log              (weekly snapshot ledger)
  batch_jobs              (Anthropic Message Batches in-flight + history)
  meeting_briefs          (rehydrated auto-briefs from nightly batches)
  attack_mapping_scratch  (per-TM rows buffered for the attack-mapping finalizer)
```

### Entity types (14)

`Service`, `Repo`, `Person`, `Endpoint`, `DataStore`, `CloudAccount`,
`Vendor`, `Control`, `Policy`, `Runbook`, `Detection`,
`AttackTechnique`, `IAMPolicy`, `Asset`.

### Relationship kinds (9)

`depends_on`, `owns`, `reports_to`, `stores_data_in`,
`authenticates_via`, `exposes`, `hosted_in`, `integrates_with`,
`has_control`.

### Provenance (4)

Every entity and relationship carries a provenance tag, which drives
the trust badge in the UI and is queryable:

- `source` — directly from an ingested doc.
- `inferred` — Claude-derived, comes with a reasoning trace.
- `claim` — something a person said, unverified.
- `user` — explicitly entered or confirmed by the user.

---

## Hard rules

These are codified in [CLAUDE.md](../CLAUDE.md) — anyone writing new
code should hold to them.

- **Two models, strict split**: `MODEL = "claude-sonnet-4-6"` for
  reasoning paths (chat, reports, threat models, design reviews, …);
  `HAIKU_MODEL = "claude-haiku-4-5-20251001"` for structured-extraction
  paths with predictable schemas. Haiku does not support extended
  thinking — strip `thinking=` from any call switched to Haiku.
- **Pre-redact at ingest**, not at send time. The invariant "if it's
  in `chunks.text_redacted`, it's already safe" beats trying to
  remember every code path.
- **Tools return pre-redacted data.** A defense-in-depth
  `apply_redactions` runs on tool results before they go back to
  Claude in `app/claude/chat.py`. Don't bypass.
- **No raw source code to Claude.** Repos are ingested as a
  `code_facts.RepoSummary`. Source files themselves are never in
  any prompt.
- **No remote embedding API.** Local sentence-transformers only.
  Privacy beats retrieval quality.
- **Anthropic SDK call shape**: `messages.parse(model=MODEL, system=[...],
  messages=[...], output_format=PydanticClass)` for interactive structured
  output; `messages.stream(...)` for chat; `messages.batches.create(requests=[...])`
  via `app/claude/batches.py` for scheduler fan-out (50% off, async,
  no `output_format` — use `tool_params_for` / `extract_validated`).
  Prompt caching via the `CACHE_5M` / `CACHE_1H` constants from
  `app/claude/caching.py`, not inline literals.
  `thinking={"type":"adaptive"}` is used **selectively** — only for
  high-stakes multi-step synthesis: `prioritization.py`, `policy_generator.py`,
  `compliance_wizard.py`, and the `security_program.py` executive brief.
  All other `messages.parse()` calls (reports, IR runbooks, plan generator,
  threat modeling, etc.) omit it intentionally for latency and cost.
- **SQLite**: single global connection guarded by `threading.Lock`.
  All writes inside `with LOCK:`. WAL mode + foreign keys on.

---

## Reference patterns

Key idioms used consistently across the codebase:

- `app/config.py`: env via `python-dotenv`, `@lru_cache get_client()`,
  `MODEL` constant, `load_prompt(name)`.
- `app/db.py`: module-level `_CONN` + `threading.Lock` + WAL +
  per-table store modules.
- Prompts as `.md` files in `prompts/`, loaded by name; never
  inlined in Python.

When adding a new feature, follow the existing module structure:
store → router → template → prompt. See [CLAUDE.md](../CLAUDE.md)
for the "where things live by purpose" table.
