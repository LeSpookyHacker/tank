# Tank — Code Tour

A narrative walkthrough of the codebase for a new contributor. This is the
**complement** to `CLAUDE.md`:

- **CLAUDE.md** = reference. "Where do I add X?" — look it up in the table.
- **TOUR.md** = narrative. "How does Tank actually *work*?" — read this start
  to finish, then go look at code.

If you read three files first, read these and skim the rest as needed:

1. `app/redact/engine.py` — the privacy chokepoint. Every byte that goes to
   Anthropic passes through `apply_redactions()`. Understand this and you
   understand the headline guarantee.
2. `app/claude/chat.py` — the streaming chat loop with tool use. The most
   complex single subsystem; everything else is simpler.
3. `app/db.py::_init_schema` — the data model. The shape of every table
   tells you what the app remembers and what it forgets.

---

## What Tank is, in three paragraphs

Tank is a local-first onboarding companion for new Sr/Staff/Manager security
engineers. You feed it your employer's docs, repos, CMDB, Sigma rules, IAM
policies, control frameworks, and people info. It builds a typed knowledge
graph locally, redacts internal identifiers before any byte leaves the
machine, and uses Claude Sonnet 4.6 to chat over the KB, generate reports,
maintain living artifacts (threat models, decisions, postmortems), and
nudge you with partner-mode behaviors (digest, journal, anniversary retros).

The headline guarantee is non-negotiable: **nothing reaches the Anthropic
API in cleartext**. Internal hostnames, emails, IPs, ARNs, account IDs, and
secrets are detected locally and replaced with stable placeholders
(`[EMAIL_001]`, `[INTERNAL_HOST_003]`, etc.) before any prompt is sent.
Responses are rehydrated locally. Secrets are SHA-256 hashed and one-way —
they can't be rehydrated even by Tank itself.

The runtime is a single FastAPI process backed by SQLite (WAL mode,
sqlite-vec for embeddings, FTS5 for keyword search). Background work — the
scheduler, ingest tasks, the chat stream — runs in a single asyncio loop
with the synchronous Anthropic SDK pushed into the default executor. There
is no separate worker process and no queue. State that needs to survive a
restart lives in SQLite.

---

## Request lifecycle: ingest → store → retrieve → chat

Two end-to-end paths. Read this as you trace through the code.

### Ingest path

```
user drops a file
    ↓
app/routers/ingest.py
    ↓
app/ingest/pipeline.py::ingest(path, category)
    ↓
dispatch by extension  ──→  app/ingest/parsers/<kind>.py
    ↓                       (markdown | pdf | docx | csv_json | image | sigma | iam | control_framework)
ParsedDocument(text, meta)
    ↓
app/ingest/chunker.py::split_with_sections   (RecursiveCharacterTextSplitter, 800/120, tiktoken)
    ↓
chunks: list[ChunkInput]
    ↓
app/redact/engine.py::apply_redactions       ← privacy chokepoint
    ↓
chunks_store.bulk_insert_chunks              (writes text_redacted + text_original)
    ↓
FTS5 + sqlite-vec indexes updated
    ↓
app/claude/extractor.py::extract_entities_for_doc   (Haiku, batched 4 chunks at a time,
                                                     semaphore=2, retries on 429)
    ↓
entities_store.upsert_entity + relationships_store.upsert_relationship
    ↓
status='ready' on the document
```

Three invariants you'll see referenced everywhere:

- Chunks are **redacted at ingest**, not at send time. `chunks.text_redacted`
  is what flows out; `chunks.text_original` is local-only forensics.
- The extractor calls Haiku, not Sonnet, and is bounded by a semaphore
  (`_EXTRACT_CONCURRENCY=2`) so bulk folder ingests can't burn the rate
  limit.
- Repos are special: they never get raw source sent to the model. They go
  through `app/ingest/code_facts.py::summarize()` which produces a
  structured `RepoSummary` (manifests, Dockerfile, CI files, grep hits,
  README), and *that* is what gets ingested as a document.

### Chat path

```
browser POSTs /api/conversations/{id}/messages
    ↓
app/routers/chat.py             (persists user msg, kicks off asyncio.Task)
    ↓
app/claude/chat.py::run_turn
    ↓
1. apply_redactions(user_text)                  ← privacy chokepoint (again)
2. hybrid_search(redacted_query, k=12)          ← app/kb/search.py: vec + FTS5 + RRF
3. entity-cards for top entities cited
4. build_system_block + build_kb_block          ← app/claude/caching.py:
                                                   the two prompt-cache breakpoints
5. messages.stream(model=MODEL, tools=KB_TOOLS, ...)
   ↓
   sync stream context manager  ──→  run in executor  ──→  events bridged via
                                                            app/claude/event_bus.py
   ↓
   for each event:
     text_delta → publish("chat.<id>", "text_delta", {...})
     tool_use   → execute_tool(name, args)    ← app/kb/tools.py
                  + apply_redactions(result)   ← defense in depth
                  → tool_result block, loop again
     end_turn   → finalize
   ↓
6. rehydrate(final_text, only-placeholders-actually-sent)
7. messages_store.append(redacted_view, display_view, citations, token usage)
8. publish("chat.<id>", "done", {message_id, token_counts, citations_count})
    ↓
browser EventSource (GET .../stream) receives the events
```

The two non-obvious moves:

- **Sync-stream-in-async bridge**: `client.messages.stream(...)` returns a
  *synchronous* context manager. We can't `await` it. So `run_turn` runs
  the stream inside `loop.run_in_executor(None, _run_stream)` and uses
  `event_bus.py` (thread-safe queues) to bridge each event back to the
  asyncio side. This is why every chat-related publish call is safe to
  call from a worker thread.
- **Scoped rehydration**: the final response is rehydrated using only the
  placeholders that actually appeared in the prompt history Claude saw —
  not the full `redaction_map`. If Claude hallucinates a placeholder we
  never sent (or a prompt-injection attempt asks for one), it stays
  redacted in the output. See `_used_placeholders` and the `sent_placeholders`
  computation in `chat.py`.

---

## The three privacy invariants

1. **Every byte to Anthropic passes `apply_redactions`.**

   Enforced at:
   - Ingest: `app/ingest/pipeline.py` calls it on every chunk before
     `chunks.text_redacted` is written. Anything later read from
     `text_redacted` is already safe.
   - Chat: `app/claude/chat.py::run_turn` calls it on the fresh user
     message (chunks are pre-redacted; user input is not).
   - Reports: `app/claude/reports.py::_build_scope_block` calls it on
     entity names and descriptions as they're inlined.
   - Vision: `app/claude/extractor.py::extract_from_diagram` calls it on
     names returned by Sonnet vision — vision sometimes surfaces internal
     hostnames the text redactor never saw.
   - Tool results: `app/claude/chat.py` re-redacts every tool_result block
     before sending it back to Claude (defense in depth — tools already
     return pre-redacted data, but we don't trust the trust).

2. **Secrets are SHA-256 one-way.**

   `app/redact/store.py::upsert_match` checks the category and, for
   `category='secret_token'`, hashes the original before insert. There is
   no path that can return the cleartext secret from `redaction_map` because
   the cleartext was never stored.

3. **Rehydration is scoped to the placeholders that were actually sent.**

   `app/claude/chat.py` computes `sent_placeholders` from the prompt
   history Claude saw and intersects that with placeholders that appear in
   the response. `load_rehydration_map(used)` then narrows the substitution
   set to exactly that intersection. A model response that names a
   placeholder we didn't send keeps the placeholder.

---

## Subsystem map

Each section names the entry point, what invariants it owns, and what
*not* to touch without a strong reason.

### `app/redact/`

The privacy chokepoint. `engine.py::apply_redactions(text)` is *the*
function. `rules.py` holds the detection rules (regex finders with
optional context windows); `secrets.py` adds `secret_token` (via
`detect-secrets` + entropy fallback) and `person_name` (spaCy, off by
default). Rule order is significant — `ALL_RULES` lists more-specific
rules first.

**Don't touch:**
- The order of entries in `ALL_RULES`. Internal hostnames must precede
  public hostnames or the public rule swallows internal hits. ARNs must
  precede AWS account IDs.
- `_resolve_overlaps` in `engine.py`. The current rule (earliest, longest
  match wins) is what makes the rest of the pipeline deterministic.
- The hash-on-insert path for `secret_token` in `store.py`. Removing it
  would silently start storing secrets cleartext.

### `app/ingest/`

Orchestrates parse → chunk → redact → persist → extract. `pipeline.py` is
the entry; parsers under `parsers/` are dispatched by extension (and by
content-sniffing for JSON/YAML — `iam.py` vs. `control_framework.py` vs.
`sigma.py` all share `.json`/`.yaml`).

**Don't touch:**
- The 800/120 chunk size/overlap in `chunker.py` without checking that
  retrieval quality holds. Picked empirically against the fixture pack.
- The `_BATCH_SIZE = 4` / `_EXTRACT_CONCURRENCY = 2` constants in
  `extractor.py`. They're tuned so a folder ingest doesn't blow the rate
  limit.

### `app/kb/`

Search, tools, entity cards, coverage analyses. `search.py::hybrid_search`
fuses vec0 (cosine over `chunks_vec.embedding`) with FTS5 (BM25 over
`chunks_fts.text_redacted`) using Reciprocal Rank Fusion. `tools.py` is
the dispatch table for the chat assistant — 15 tools, all returning
pre-redacted data. `entities.py` builds entity cards (the typed view of a
service / person / data store with linked chunks).

**Don't touch:**
- The RRF constant in `search.py` without understanding why the current
  value balances vec and FTS rankings.
- The defense-in-depth re-redact in `chat.py` that runs over tool results.
  Even though tools return pre-redacted data, the second pass catches
  anything an upstream change might leak.

### `app/claude/`

Everything that calls Claude. The three flagship modules:

- `chat.py` — streaming chat with tool use. See the lifecycle section
  above. Most complex single file in the codebase.
- `scheduler.py` — single asyncio.Task that owns every recurring job
  (digest, reflection, journal, anniversary, snapshots, backup). The
  durable last-fired contract lives in `scheduler_state_store`.
- `reports.py` — 14 report generators sharing a cached scope block.
  Running multiple reports against the same scope reuses the prompt cache
  → ~2x cheaper than cold runs.

Living artifacts (threat models, decisions, design reviews, postmortems,
tabletops, IR runbooks) follow the same pattern: a `<artifact>s_store.py`
under `app/storage/`, a `<artifact>.py` under `app/claude/`, a prompt
under `prompts/`, and a router. `threat_modeling.py` is the canonical
reference — versioned, drift-aware regen.

**Don't touch:**
- The asyncio/sync bridge in `chat.py::run_turn`. The `run_in_executor` +
  event-bus pattern is what makes the sync SDK stream usable from async
  code.
- The `_MAX_TOOL_ITERATIONS = 8` cap. Most turns finish in 1–3; the cap
  is what stops a runaway tool-call cycle.
- The order of `_tick` branches in `scheduler.py`. The clock-comparison
  pattern (`hhmm >= "HH:MM"`) plus `has_fired(key, label)` is what makes
  same-day re-firing impossible across restarts.

### `app/db.py`

Single global SQLite connection, guarded by a module-level
`threading.Lock`. All writes go inside `with LOCK:`. WAL mode + foreign
keys on. `_init_schema` runs the full `CREATE TABLE IF NOT EXISTS` script
on every connection; the `_migrate_*` functions are additive ALTER /
CREATE-IF-NOT-EXISTS that run after.

**Don't touch:**
- Migration order in `_init_schema`. Old databases replay the whole list
  on every boot; reordering or removing entries breaks them.
- The lock pattern. SQLite serializes writes; without the explicit lock
  in storage modules, concurrent ingests would race.

### `app/claude/event_bus.py`

Tiny pub/sub built on `asyncio.Queue` per subscriber. Every SSE endpoint
in the codebase reads from a topic via this. Multi-tab safe — both tabs
get every event because each subscriber has its own queue. Cleans up
topics when the last subscriber unsubscribes.

---

## The scheduler clock

Every recurring job in one table. All times are in the scheduler's local
timezone (set `TANK_TIMEZONE=America/Los_Angeles` in `.env` for hosted
VMs that run in UTC).

| Time            | Job                          | Cadence             | Idempotency label | Notes                                  |
| --------------- | ---------------------------- | ------------------- | ----------------- | -------------------------------------- |
| `digest_time`   | `_fire_digest`               | Daily               | YYYY-MM-DD        | User-configurable in `app_state`       |
| `16:00`         | `_fire_reflection`           | Weekly (Friday)     | YYYY-MM-DD        | `reflection_day` configurable          |
| `18:00`         | `_fire_journal_prompt`       | Mon–Fri             | YYYY-MM-DD        | Skipped if today's journal exists      |
| `22:00`         | `_fire_auto_briefs`          | Daily               | YYYY-MM-DD        | Cap 5/night; 4h–36h lookahead          |
| `Sun 03:00`     | `_fire_weekly_backup`        | Weekly              | YYYY-WNN          | Retains last 8; online `.backup()`     |
| `Sun 09:00`     | `_fire_attack_surface_snapshot` | Weekly           | YYYY-WNN          |                                        |
| `Sun 09:30`     | `_fire_security_program_snapshot` | Weekly         | YYYY-WNN          |                                        |
| Tenure day ∈ {30, 60, 90, 180, 365} | `_maybe_anniversary` | One-shot per milestone | Per-kind report row | Generic retro + security retro + philosophy doc |

Constants for all the time literals live at the top of
`app/claude/scheduler.py` (`_REFLECTION_TIME`, `_JOURNAL_TIME`, etc.). If
you need to change a time, change it there — *don't* search-and-replace.

---

## Where to add X — worked examples

The CLAUDE.md table is a quick reference. These three walk through the
end-to-end shape of an addition.

### Example 1: add a new redaction category

Goal: redact internal Slack channel names like `#sec-prod-incidents`.

1. **Detector**: add a finder in `app/redact/rules.py`. Use a context-word
   gate if the pattern is ambiguous (e.g. require `slack`, `channel`
   nearby).

   ```python
   SLACK_CHAN_RE = re.compile(r"#[a-z0-9][a-z0-9-]{1,40}")

   def find_slack_channels(text: str) -> list[Match]:
       out: list[Match] = []
       for m in SLACK_CHAN_RE.finditer(text):
           if _has_context(text, m.start(), m.end(), ("slack", "channel")):
               out.append(Match(m.start(), m.end(), m.group(0), "slack_channel"))
       return out
   ```

2. **Register** in `ALL_RULES`. Put it before any more-general rule that
   could swallow its matches.

3. **Test**: add a case to `tests/test_redaction.py`. The fixture pack
   already plants identifiers; if you add a new category, plant one too
   and verify `verify_privacy --fixture-pack` exits 0.

4. **No engine change needed.** The placeholder format follows the rule's
   `placeholder_fmt`; the engine and `_PLACEHOLDER_RE` in `chat.py`
   discover the prefix automatically.

### Example 2: add a chat tool

Goal: give the chat assistant a way to look up which on-call rotation a
service belongs to.

1. **Schema**: append an entry to `TOOL_SCHEMAS` in `app/kb/tools.py`
   using Anthropic's tool-use shape (`name`, `description`,
   `input_schema`). The `description` matters — it's how Claude decides
   when to use the tool.

2. **Dispatch**: add a branch to `execute_tool(name, args)` further down
   in the same file. Return a JSON-serializable dict. **Do not call
   `apply_redactions` here** — return pre-redacted data the way every
   other tool does. The defense-in-depth pass in `chat.py` will redact
   the serialized result before it goes back to Claude.

3. **Test it cold**: start the server, open chat, ask a question that
   should trigger it. The SSE event log in the browser shows
   `tool_use` / `tool_result` events.

### Example 3: add a new report kind

Goal: a "third-party vendor risk" report.

1. **Pydantic schema**: add `VendorRiskReport` (or similar) to
   `app/schemas.py`.

2. **Prompt**: drop `prompts/report_vendor_risk.md`. Use the existing
   reports' prompts as a template. They read the scope block as a user
   message and emit JSON conforming to the schema.

3. **Generator**: add a function in `app/claude/reports.py` that calls
   `_run("report_vendor_risk", VendorRiskReport)`, renders the result
   to markdown, and calls `_finalize(kind="vendor_risk", ...)`.

4. **Register** in `REPORT_REGISTRY` at the bottom of `reports.py`. This
   one line is what the scheduler and the router both use to dispatch.

5. **Router case**: add a branch in `app/routers/reports.py::generate_report`.

6. **No DB change needed.** The `reports` table is kind-agnostic.

---

## Gotchas a new contributor will hit

- **Python 3.9 vs 3.11.** The codebase runs on 3.9 (dev box constraint)
  thanks to Pydantic 2 + a vendored `eval_type_backport`. Production
  target is 3.11+ because `sqlite-vec` requires `enable_load_extension`,
  which macOS system Python 3.9 lacks. Vector search degrades gracefully
  to FTS5-only when the extension isn't loaded.

- **Sync SDK stream in an async loop.** The Anthropic SDK's
  `messages.stream(...)` is a synchronous context manager. Do not try to
  `await` it. The pattern in `chat.py::run_turn` is the canonical example
  — wrap the call in a function, run it in the default executor, bridge
  events through `event_bus.py`. Any new code that needs to stream should
  do the same.

- **Prompt-cache breakpoints.** Only two stable cache breakpoints exist:
  the system block (`build_system_block`) and the KB block
  (`build_kb_block`), both in `app/claude/caching.py`. Both return blocks
  with `cache_control={"type":"ephemeral"}`. If you add a new caller, get
  cache hits by reusing those builders — don't roll your own.

- **`log_token_usage()` must be called.** Every Claude call must invoke
  `app/config.py::log_token_usage(call_site, model, usage)` after getting
  a response. Skipping it means the spend is invisible in
  `/api/usage/cost`. Grep for `log_token_usage` to see the pattern.

- **`with LOCK:` for all writes.** The single global SQLite connection is
  shared across all threads (`check_same_thread=False`). Writes that
  don't take `LOCK` will race under load. Storage modules already do
  this; if you add a new store module, mirror the pattern.

- **Migrations are additive and idempotent only.** Never reorder, rename,
  or remove a `_migrate_*` function in `app/db.py`. Old databases replay
  the whole list on every boot. The pattern is `_add_col_safe()` (ALTER
  TABLE ADD COLUMN guarded by `PRAGMA table_info`) or `CREATE TABLE IF
  NOT EXISTS` plus `IF EXISTS`-guarded backfills.

- **No raw source code to Claude.** Repos are summarized locally via
  `app/ingest/code_facts.py::summarize()` and only the structured summary
  (manifests, Dockerfile, CI files, grep hits, README) is ingested as a
  document. Source files themselves never appear in any prompt. Don't
  build a code-aware feature that breaks this.

- **No remote embeddings.** `app/ingest/embedder.py` uses local
  sentence-transformers (`all-MiniLM-L6-v2`, 384-dim). Don't swap in a
  remote embedding API "for quality" — privacy beats retrieval quality.

- **Haiku does not support extended thinking.** If you switch a Sonnet
  call to `HAIKU_MODEL` for cost reasons, remove `thinking=...` from the
  request or it will error.

- **TANK_TIMEZONE matters.** Hosted VMs run in UTC by default. The
  scheduler uses local time for all clock comparisons, so a user whose
  `digest_time = 08:00` and runs in UTC gets the digest at 08:00 UTC,
  which is probably not what they want. Set `TANK_TIMEZONE` to the IANA
  zone in `.env`.

- **The fixture pack is your friend.** `python -m scripts._gen_fixtures`
  + `python -m scripts.load_fixtures` populates a realistic KB.
  `python -m scripts.verify_privacy --fixture-pack` is a black-box
  privacy assertion (exit 0 = nothing leaked). Run it any time you
  change ingest, redaction, or storage.
