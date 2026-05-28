# Quickstart

Get Tank running in under 10 minutes.

---

## Prerequisites

| Requirement | Why | How to check |
|-------------|-----|--------------|
| Python 3.11+ | `sqlite-vec` extension + Pydantic 2 union syntax | `python3 --version` |
| Anthropic API key | Tank calls `claude-sonnet-4-6` for every analysis | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| macOS or Linux | Windows is untested | — |
| ~500 MB free disk | Embedding model + SQLite DB | `df -h ~` |
| Internet access to `api.anthropic.com` | Only external endpoint Tank uses | — |

> ⚠️ **Warning:** macOS ships Python 3.9 at `/usr/bin/python3`. That version will not work. Install 3.11+ via Homebrew: `brew install python@3.12`.

---

## Install

```bash
git clone https://github.com/LeSpookyHacker/tank.git tank
cd tank
cp .env.example .env
```

Open `.env` in your editor and set your API key:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Then start Tank:

```bash
./scripts/start.sh
```

Expected output on first run:

```
✓ Python 3.12.x found
✓ Creating .venv and installing dependencies...
✓ ANTHROPIC_API_KEY found
✓ Database initialized at ~/.tank/db.sqlite
✓ Starting uvicorn on http://127.0.0.1:8000
```

Your browser opens to `http://localhost:8000` and redirects to the onboarding flow.

> 📝 **Note:** Dependency installation takes 2–3 minutes the first time (downloads the local embedding model). Subsequent starts are instant because the environment is cached.

---

## Verify it's working

Open a second terminal and run:

```bash
curl http://127.0.0.1:8000/healthz
```

Expected response:

```json
{"ok": true, "scheduler": "running", "db": "ok"}
```

Then open a chat in the side panel and type:

```
hello
```

You should get a response. That confirms the API key works and the Claude connection is live.

---

## Top 3 failure points

### `start.sh` exits with "Python 3.9 found, need 3.11+"

macOS system Python is too old. Fix:

```bash
brew install python@3.12
# Open a new shell so the updated PATH takes effect, then retry:
./scripts/start.sh
```

### `start.sh` exits with "ANTHROPIC_API_KEY is empty"

The `.env` file is missing or the key isn't pasted in. Fix:

```bash
cp .env.example .env
# Edit .env and paste your key, then retry.
```

### Chat returns an error about the API

Your key may be invalid or have no credits. Verify at [console.anthropic.com](https://console.anthropic.com) and confirm the key starts with `sk-ant-`. Check `curl http://127.0.0.1:8000/healthz` still returns `"ok": true`.

---

## Next steps

| What | Where |
|------|-------|
| Full install options (VM, systemd, SSH tunnel) | [installation.md](installation.md) |
| The intake interview (15-minute company setup, no docs needed) | [first-run.md](first-run.md) |
| Feature reference by nav group | [features/README.md](features/README.md) |
| All environment variable options | [configuration.md](configuration.md) |
| Day-to-day workflows | [using-tank.md](using-tank.md) |
| How Tank works internally | [architecture.md](architecture.md) |
| Common questions | [faq.md](faq.md) |
