# Contributing to Tank

Thank you for your interest in contributing! Tank is a local-first security engineering
partner, and we welcome bug reports, documentation improvements, and pull requests.

Please read this guide before opening an issue or PR, and review our
[Code of Conduct](CODE_OF_CONDUCT.md) before participating.

---

## Quick setup

```bash
git clone https://github.com/LeSpookyHacker/tank.git tank
cd tank
cp .env.example .env        # add your key from console.anthropic.com
./scripts/start.sh          # creates .venv, installs deps, starts the server
```

---

## Running the tests

```bash
source .venv/bin/activate
python -m pytest -q         # 53 tests — no API key required
```

Tests cover the redaction engine, ownership logic, and ingest path guards. They run
entirely offline. Integration paths (chat, ingest, reports) require manual testing with
the sample data — see `docs/contributing.md` for the full workflow.

---

## Non-negotiable rules

**Privacy contract** — every code path that calls the Anthropic API must pass user-facing
text through `apply_redactions(text)` (`app/redact/engine.py`) before sending, and
rehydrate the response afterward with `rehydrate(text, load_rehydration_map(...))`.
Skipping this is a security bug, not a style issue.

**Two-model split** — use `MODEL` (`claude-sonnet-4-6`) for reasoning tasks and
`HAIKU_MODEL` (`claude-haiku-4-5-20251001`) for structured-extraction tasks with
predictable JSON schemas. Do not add `thinking=...` to Haiku calls; it is unsupported.

**Token tracking** — every Claude call must invoke `app.config.log_token_usage(call_site,
model, usage)` after getting a response, or the spend is invisible to the cost dashboard.

**SQLite writes** — all writes go inside `with LOCK:` (the module-level lock in
`app/db.py`). Do not write outside the lock.

---

## Pull request process

1. **One concern per PR.** A bug fix does not need unrelated cleanup.
2. **Reference an issue.** Every PR should close or reference at least one open issue.
3. **Run the tests.** Confirm `python -m pytest -q` passes before submitting.
4. **Privacy impact statement.** If your change touches redaction, prompt assembly, or any
   Claude call path, state explicitly in the PR description that you reviewed the privacy
   contract and why the change is safe.

---

## Commit message format

```
<area>: <short imperative description>

<optional body: what was done and why>
```

- Lowercase subject line, under 72 characters, no trailing period.
- Examples: `fix: escape LIKE wildcards in find_for_technique`, `feat: add risk register`

---

## Full contributing guide

For detailed guidance on code style, filing bug reports, requesting features, and testing
with the synthetic sample data, see [`docs/contributing.md`](docs/contributing.md).
