# Configuration Reference

All Tank configuration lives in `.env` at the project root. Copy `.env.example` to `.env` once, then edit it — you never need to touch the source files.

```bash
cp .env.example .env
```

---

## All environment variables

### Required

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ANTHROPIC_API_KEY` | string | — | Your Anthropic API key. Required to start. Get one at [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys). |

### Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_DB_PATH` | path | `~/.tank/db.sqlite` | Path to the SQLite database file. Override if you want to keep the DB somewhere other than your home directory, or to run multiple isolated Tank instances. |

### Network

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_BIND_HOST` | string | `127.0.0.1` | Host uvicorn listens on. Keep at `127.0.0.1` unless you are putting Tank behind a reverse proxy. Never bind to `0.0.0.0` without a firewall rule in front. |
| `TANK_BIND_PORT` | integer | `8000` | Port uvicorn listens on. Change if 8000 conflicts with another service. |
| `TANK_API_KEY` | string | `""` (disabled) | Optional static API key. When set, every HTTP request to Tank must include either a valid session cookie or an `X-Tank-Key: <value>` header (both compared via `secrets.compare_digest`). Exempted paths: `/healthz`, `/static/*`, `/api/auth/*`. The browser UI authenticates via an HttpOnly session cookie issued by `POST /api/auth/session` (Settings → enter your key → Login). Strongly recommended if `TANK_BIND_HOST` is changed from `127.0.0.1`. Generate a secure key with: `python3 -c "import secrets; print(secrets.token_hex(32))"`. |

### Redaction

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_INTERNAL_TLD` | string | `""` (disabled) | Your employer's internal top-level domain (e.g. `acme.internal`). Hostnames ending in this TLD are redacted before any Claude call. The built-in list (`.internal`, `.corp`, `.local`, `.lan`, `.intra`) always applies regardless. |
| `TANK_ENABLE_PERSON_REDACTION` | `1` or unset | unset | Set to `1` to enable NER-based person-name redaction. Requires `spaCy` with a language model, which needs Python 3.10+. Off by default because spaCy is not installable on Python 3.9. |

### Scheduler and digest

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_DIGEST_TIME` | `HH:MM` | `08:00` | Time of day (24-hour, local time) the morning digest fires. Nudges, subscribed reports, and anniversary checks all run at this time. |
| `TANK_TIMEZONE` | IANA tz name | `""` (system TZ) | Timezone for the scheduler. **Critical on a UTC VM** — if unset, Tank uses the system timezone (UTC on most cloud VMs), which means your 08:00 digest fires at midnight local time. Set this to your actual timezone, e.g. `America/Los_Angeles`. |

### Runtime mode

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_ENV` | `dev` or `prod` | `dev` | `dev` enables uvicorn `--reload` (auto-restart on code changes). `prod` disables it. Always set `prod` on a VM under systemd — the `install-systemd.sh` script forces this in the unit file regardless of `.env`. |

### Anthropic SDK

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_API_MAX_RETRIES` | integer | `4` | Number of times the SDK retries on 5xx, 429, or connection errors with exponential backoff. Increase on a flaky network; decrease to fail fast during development. |
| `TANK_API_TIMEOUT_SECONDS` | float | `600` | Per-request timeout ceiling in seconds. 600s (10 minutes) accommodates the longest report generations. Reduce during development if you want faster failures. |
| `TANK_TOOL_TOKEN_EFFICIENT` | `1` or unset | unset | Set to `1` to opt into Anthropic's `token-efficient-tools-2025-02-19` beta header on the chat path. Reduces tool-use protocol overhead by ~14% on tool-heavy turns. Gated by flag so a regression can be flipped off without a deploy. Has no effect on non-chat call sites. |

### Debugging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_DEBUG_TOKENS` | `1` or unset | unset | Set to `1` to log per-call token counts (input, output, cache_read, cache_create) to the console for every Claude call. Useful for understanding cost and cache hit rates. Produces substantial log output — don't leave on in prod. |

### Integrations

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TANK_NYX_API_KEY` | string | `""` (disabled) | If set, the vulnerability intake endpoint (`POST /api/vulnerabilities/intake`) requires an `X-Nyx-Key` header matching this value. Leave unset unless you are connecting the [Nyx](https://github.com/LeSpookyHacker/nyx) disclosure-triage tool. |

---

## Annotated `.env` example

This is a complete example for a dev-VM deployment. Copy and adjust.

```bash
# ── Required ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# ── Database ──────────────────────────────────────────────────────────────────
# Default is fine for most users. Override if you have multiple Tank instances.
# TANK_DB_PATH=/data/tank/db.sqlite

# ── Network ───────────────────────────────────────────────────────────────────
# Keep 127.0.0.1 unless you put Tank behind a reverse proxy.
TANK_BIND_HOST=127.0.0.1
TANK_BIND_PORT=8000
# Optional API key — strongly recommended if TANK_BIND_HOST is not 127.0.0.1.
# Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
# TANK_API_KEY=your-64-char-hex-token-here

# ── Redaction ─────────────────────────────────────────────────────────────────
# Replace with your employer's internal domain.
TANK_INTERNAL_TLD=acme.internal
# Uncomment if you have Python 3.10+ and want person-name redaction.
# TANK_ENABLE_PERSON_REDACTION=1

# ── Scheduler ─────────────────────────────────────────────────────────────────
# Your local time, not the VM's timezone. The VM is probably UTC.
TANK_TIMEZONE=America/Los_Angeles
TANK_DIGEST_TIME=08:00

# ── Runtime ───────────────────────────────────────────────────────────────────
# Use 'prod' on a VM under systemd. 'dev' enables hot-reload.
TANK_ENV=prod

# ── Anthropic SDK ─────────────────────────────────────────────────────────────
# Increase retries on a flaky network.
TANK_API_MAX_RETRIES=4
TANK_API_TIMEOUT_SECONDS=600

# ── Debugging ─────────────────────────────────────────────────────────────────
# Uncomment to log per-call token counts to the console.
# TANK_DEBUG_TOKENS=1
# Uncomment to enable Anthropic's token-efficient tools beta on chat (~14% savings).
# TANK_TOOL_TOKEN_EFFICIENT=1

# ── Integrations ──────────────────────────────────────────────────────────────
# Uncomment and set if you connect the Nyx disclosure-triage tool.
# TANK_NYX_API_KEY=your-nyx-api-key-here
```

---

## Where to go next

- [installation.md](installation.md) — full install walkthrough including VM setup and systemd
- [operations.md](operations.md) — runtime ops: healthcheck, backup, scheduler, time zone troubleshooting
- [troubleshooting.md](troubleshooting.md) — what to do when something goes wrong
