# Contributing

---

## Development environment setup

Tank runs on Python 3.9 for local development (the redaction engine and all tests work on 3.9). Production targets 3.11+. If you only have 3.9, that is fine for coding and running tests — you will lose vector search but FTS5 keyword search still works.

```bash
git clone https://github.com/LeSpookyHacker/tank.git tank
cd tank
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env (required to run the server; not required for tests)
./scripts/start.sh
```

`start.sh` creates `.venv/`, installs all dependencies, initializes `~/.tank/db.sqlite`, and starts uvicorn on `http://127.0.0.1:8000`. Kill it with `Ctrl-C` when you want to develop.

For hot-reload during development (auto-restart on file save), `TANK_ENV=dev` (the default) enables uvicorn `--reload`.

---

## Running the test suite

```bash
source .venv/bin/activate
python -m pytest -q
```

The test suite covers the redaction engine. There are 28 tests today. Expected output:

```
28 passed in 0.Xs
```

Run a single test by name:

```bash
python -m pytest tests/test_redaction.py::test_email_redacted -v
```

Filter by keyword:

```bash
python -m pytest -k "secret" -v
```

> 📝 **Note:** Tests do not require an `ANTHROPIC_API_KEY`. They exercise the redaction engine in isolation. Integration tests (chat, ingest, reports) are not automated — test those paths manually after changes.

---

## Testing sample data

To test all features end-to-end without real employer data, load the synthetic "MedScribe-R-Us" fixture set:

```bash
source .venv/bin/activate
python -m scripts._gen_fixtures             # generate PDF/DOCX/PNG fixtures
python -m scripts.load_fixtures --dry-run   # preview ingest plan (no API calls)
python -m scripts.load_fixtures             # ingest (uses ~$5-10 in API spend)
python -m scripts.seed_db                   # seed living artifacts (no API cost)
```

Then verify nothing leaked:

```bash
python -m scripts.verify_privacy --fixture-pack
# → PRIVACY ASSERTION PASSED.
```

---

## Code style and standards

**Comments:** Write comments only when the *why* is non-obvious — a hidden constraint, a specific bug worked around, behavior that would surprise a reader. Do not describe what the code does; well-named identifiers do that.

**Pydantic:** The codebase uses Pydantic 2 with `X | Y` union syntax throughout. On Python 3.9, this requires `eval_type_backport` (already in `requirements.txt`). Do not replace with `Optional[X]` — consistency matters more than 3.9 friendliness.

**Privacy rule (non-negotiable):** Every path that calls the Anthropic API must run user-facing text through `apply_redactions(text)` first. After getting a response, rehydrate with `rehydrate(text, load_rehydration_map(used_placeholders))`. If you add a new Claude call and skip redaction, it's a security bug.

**No raw source code to Claude:** Repos are ingested as a `code_facts.RepoSummary`. Source files are never in any prompt. This eliminates the code-exfiltration failure mode.

**Two models, strict split:**
- `MODEL = "claude-sonnet-4-6"` — chat, reports, threat models, design reviews, postmortems, tabletops, DFD analysis, vision.
- `HAIKU_MODEL = "claude-haiku-4-5-20251001"` — structured-extraction tasks with predictable JSON schemas (entity extraction, meeting prep, journal/lesson extraction, nudge generation).
- Do not add `thinking=...` to Haiku calls — Haiku does not support extended thinking.

**Token tracking:** Every Claude call must call `app.config.log_token_usage(call_site, model, usage)` after getting a response. Without it, that spend is invisible to the cost counter at `/api/usage/cost`.

**SQLite writes:** All writes go inside `with LOCK:` (the module-level lock in `app/db.py`). Do not write outside the lock.

**Prompt files:** All Claude prompts live as `.md` files in `prompts/`. Load them with `config.load_prompt(name)`. Do not inline prompts in Python code.

---

## Filing a bug report

Include the following in every bug report:

1. **Platform:** `uname -a && python3 --version`
2. **Commit:** `git rev-parse HEAD`
3. **Error text:** the full stack trace or error message from the logs
4. **Token debug output** (if the bug involves a Claude response):
   ```bash
   TANK_DEBUG_TOKENS=1 uvicorn app.main:app --reload
   ```
   Copy the `[tokens]` lines from the console.
5. **Steps to reproduce:** what you were doing when it happened
6. **Redacted logs** (remove anything personal before pasting):
   ```bash
   journalctl --user -u tank --since "1 hour ago" > /tmp/tank.log
   ```

Open an issue at [github.com/LeSpookyHacker/tank/issues](https://github.com/LeSpookyHacker/tank/issues).

---

## Requesting a feature

Before opening a feature request, check:

1. Is this covered by an existing feature? See [docs/features/](features/README.md) for the full list.
2. Does this touch the privacy boundary? Any feature that changes what reaches the Anthropic API needs a clear explanation of why it does not compromise the privacy guarantee.

Open an issue describing: the problem you're solving, how you'd expect it to work, and which existing pattern it's closest to (e.g., "like how DFD analysis works but for X").

---

## Pull request process

- **One concern per PR.** A bug fix doesn't need surrounding refactoring; a feature doesn't need unrelated cleanup.
- **Reference the issue.** Every PR should close or reference at least one open issue.
- **Test before submitting.** Run `python -m pytest -q` and confirm it passes. If your change touches a Claude call path, test it manually with the sample data.
- **Privacy impact statement.** If your change touches redaction, prompt assembly, or any Claude call path, state explicitly in the PR description that you reviewed the privacy contract and explain why the change is safe.

---

## Commit message format

Follow the pattern used in the existing history:

```
<area>: <short imperative description>

<optional body: what was done and why>
```

Examples from the repo:

```
security: adversarial audit pass 2 — 16 vulnerabilities fixed + docs update
docs: update README, HISTORY, and feature docs for security audit pass
feat: add risk register, security program dashboard, IR runbooks
```

Keep the subject line under 72 characters. Use lowercase. No trailing period.
