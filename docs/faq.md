# FAQ

Common questions, grouped by theme. For step-by-step setup, see
[installation.md](installation.md). For things that go wrong at
runtime, see [troubleshooting.md](troubleshooting.md).

---

## Privacy

### Does my employer's data leave the machine?

Only **redacted** chunks + redacted user prompts go to Anthropic.
The redaction map stays on your laptop / VM forever. The redaction
chokepoint is `app/redact/engine.py::apply_redactions(text)`; every
byte that reaches the Claude API passes through it.

### What's redacted by default?

Emails, internal hostnames (your TLD + the common ones:
`.internal`, `.corp`, `.local`, `.lan`, `.intra`), private IPv4
(RFC1918 / loopback / link-local / CGNAT / ULA), AWS account IDs,
AWS ARNs, GCP project IDs, Azure subscription/tenant UUIDs, and
**secret tokens** (via `detect-secrets` + Shannon entropy).

Off by default (toggle in Settings): public hostnames, public IPs,
person names.

### Are secrets ever recoverable?

No. For `category='secret_token'`, the `redaction_map.original_text`
column is overwritten with `sha256(original)` at insert time. Tank
cannot rehydrate secrets even if it wanted to. You look up the
actual secret in the source doc yourself.

### How do I verify nothing leaked?

```bash
source .venv/bin/activate
python -m scripts.verify_privacy --fixture-pack
```

Greps every column that gets sent to Claude
(`chunks.text_redacted`, `messages.redacted_view`,
`reports.content_md_redacted`, `journal_entries.body_redacted`,
`notes.body_redacted`) for any of the planted fixture identifiers.
Exit 0 = pass.

### Why local embeddings instead of Anthropic / OpenAI / Voyage?

Privacy beats retrieval quality. Even the *redacted* chunks shouldn't
go through a second vendor's wire. Local
`sentence-transformers/all-MiniLM-L6-v2` is good enough for the
~5k-100k chunk corpus a single user will accumulate.

### Why no raw source code to Claude?

Repos are ingested as a `code_facts.RepoSummary` — language LOC,
dependency manifests, Dockerfile facts, CI workflow files,
auth/secrets grep hits, CODEOWNERS, README, ARCHITECTURE.md.
Source files themselves are never in any prompt. This eliminates
the "Tank exfiltrated proprietary code" failure mode.

---

## Cost

### How much does running Tank cost?

Ballpark for a real ~200-doc / ~30-repo employer corpus:

- **Initial ingest** (entity extraction over chunks): $8-12 one time.
- **Six original reports**: $0.50-1.00 each, generated once. Or
  subscribe them to a monthly cadence ~ $5-10/month.
- **Daily chat**: ~$0.50/day on average.
- **Threat-model generation** (one per service, ~8 services for a
  mid-size company): ~$0.30-$0.40 total. Regeneration on drift adds
  $0.02-$0.05 per event.
- **Phase 14 reports** (`attack_mapping`, `iam_audit`): $0.05-$0.20
  each. Run monthly.
- **Phase 15 hooks** (lesson extraction, glossary discover,
  philosophy seed/evolve): $0.05-$0.10/month combined.

Total: typical engineer's daily use lands around **$15-25/month**
including periodic report runs. The Anthropic dashboard tracks
spend per API key — recommended to use a dedicated key for Tank.

### Why is there no cost cap?

Phase 8+ should add one. Today the rate limits are: nudges
(max 2/day), auto pre-meeting briefs (max 5/night), one anniversary
report fires once per milestone. Heavy usage scales linearly with
chat volume.

### Can I run Tank without an API key for testing?

Mostly no. The redaction engine works without a key (and the test
suite uses it offline). But ingest, chat, reports, and every Phase
12+ feature need Sonnet. There's no "offline mode" today.

---

## Setup

### Why Python 3.11+?

Two reasons: `sqlite-vec`'s extension load requires
`enable_load_extension` (macOS system Python 3.9 is built without
it), and Pydantic 2's `X | Y` union syntax was added in 3.10. Tank
uses both throughout.

The codebase technically runs on 3.9 thanks to `eval_type_backport`,
but you'll lose vector search and the experience degrades.

### Why a dev VM instead of just running on my laptop?

Mostly because Tank is at its best **always-on**:

- The morning digest fires at 08:00 every day, regardless of
  whether your laptop is awake.
- The evening journal prompt at 18:00.
- The Sunday weekly backup at 03:00.
- The auto pre-meeting briefs at 22:00.
- Anniversary retros fire on the actual milestone day.

If Tank lives on your laptop and you close the lid every night,
half the scheduler jobs miss. A dev VM that's always reachable via
SSH tunnel costs you nothing operationally and gives you the full
behavior.

### Can I run Tank on a work laptop without permission?

Probably not — check your acceptable-use policy. The Anthropic API
call alone may require approval. The privacy guarantee (no
cleartext to Anthropic) makes the legal case easier than "use
GPT-4 with your prod data," but **don't skip the conversation**.

### Can I share a Tank install with my team?

No. Tank is single-user by design — single SQLite connection
guarded by `threading.Lock`, single `user_id` in `owned_entities`.
Each engineer should run their own. Maybe Tank Pro will go
multi-tenant; today it doesn't.

---

## Daily use

### What's the difference between a nudge and a follow-up?

- **Nudges** are tool-generated. Tank notices something (a
  contradiction, a drift, an abandoned thread) and surfaces a card.
  Snooze / dismiss / act. They expire if you don't act.
- **Follow-ups** are user-tracked. You explicitly add them — from a
  chat suggestion, a meeting brief, a postmortem action item, or
  the inline `+ add` on the home dashboard. They have due dates
  and stay open until you close them.

### Does Tank ever modify external systems?

No. Tank reads only. It doesn't open Jira tickets, push to GitHub,
page on-call, send Slack messages, or modify IAM. By design — the
ability to write is a much larger blast radius and would require an
auth layer Tank doesn't have today.

The Phase 11 connectors (CVE feed, GitHub poller) are
**read-only**: they pull data in, never push.

### How do I correct Tank when it's wrong?

Every assistant message has a **"This was wrong"** button. It opens
a small form that creates a note tagged `provenance='user'` and
disputes the conflicting entity attr. Tank remembers the
correction.

For more invasive edits, just chat: *"actually, payments-api is
owned by Sam, not Marcus."* The notes-to-KB diff extractor proposes
the change; you confirm; it commits with `provenance='user'`.

### What's the "lens" thing on the home page?

[app/role.py::current_lens()](../app/role.py) returns one of `map`,
`prioritize`, `execute`, `maintain` based on
`app_state.tenure_started_at`:

- **Day 1-14: Map** — coverage, who-owns-what, fast wins.
- **Day 15-60: Prioritize** — risk ranking, gap closure, control coverage.
- **Day 61-180: Execute** — ongoing initiatives, decision logs.
- **Day 180+: Maintain** — drift, freshness, succession.

The chat system prompt loads `chat_lens_<lens>.md` at runtime, so
Tank's tone and emphasis shift automatically.

### Will Tank still be useful at 18 months?

That's the Phase 15 bet. The lessons DB, glossary, philosophy doc,
ownership dashboard, and `maintain` lens all start paying off after
the initial 90 days. Whether they actually deliver depends on
whether you use them — none of this works if you stop ingesting
new docs / writing postmortems in Tank.

---

## Architecture & extension

### Can I run Tank against a different model?

Today, no. `MODEL = "claude-sonnet-4-6"` is hard-coded in
`app/config.py` and every Claude call site uses it. Uniform prompt-
cache behavior depends on this. To swap, you'd update the constant
and re-verify every prompt's tone (some are tuned for Sonnet 4.6's
adaptive thinking).

### Can I add my own report kind?

Yes:

1. Add a Pydantic output schema to [app/schemas.py](../app/schemas.py).
2. Add a generator function to
   [app/claude/reports.py](../app/claude/reports.py) that calls
   `_run(prompt_name, OutputType)` and renders Markdown.
3. Add the generator to `REPORT_REGISTRY`.
4. Add a prompt file at `prompts/report_<kind>.md`.

[CLAUDE.md](../CLAUDE.md) has a "where things live by purpose" table
that maps every common extension to its files.

### Can I add my own chat tool?

Yes:

1. Define the schema in `TOOL_SCHEMAS` in [app/kb/tools.py](../app/kb/tools.py).
2. Add a dispatch branch in `execute_tool(name, args)`.
3. Make sure the tool's return value flows through pre-redacted
   data (or runs through `apply_redactions` before returning).

### Why no Web UI for everything?

Tank's templates are server-rendered Jinja2 + HTMX. Light JS. No
React, no SPA, no bundler. The bet: a security engineer using this
for hours a day cares more about "loads in 30ms" than a flashy UI.
If you want to swap out the front-end, the API surface is REST +
SSE — should be straightforward.

---

## Name & origin

### Why "Tank"?

Tank in *The Matrix* was the operator. He stayed on the ship,
watching the screens, feeding Neo & Trinity context, maps, and
answers when they were in the field. That's the role for a security
engineer's first 90 days — making sense of unfamiliar terrain fast
enough to be useful.

### Is the name a reference to "tanking"?

No. (Though if you're getting flamed in production, Tank can help
with the postmortem.)
