# Installation

Two recommended setups: local laptop (for trying it out) and an
always-on dev VM with systemd (for real use). Pick one.

---

## Prerequisites

| Thing | Why | Notes |
| --- | --- | --- |
| Python 3.11+ | sqlite-vec extension load + Pydantic 2 union syntax | macOS system Python is 3.9 — get 3.11+ from Homebrew (`brew install python@3.12`) or python.org |
| Anthropic API key | Tank uses `claude-sonnet-4-6` for every Claude call | Get one at [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| ~500MB disk | Local embedder model + sqlite DB + WAL + backups | Grows over time as you ingest. Plan for 1-2GB after a year |
| Internet to `api.anthropic.com` | The only outbound endpoint Tank uses by default | Optional connectors (CVE feed, GitHub) add more outbound when enabled |

---

## Local laptop install

```bash
git clone <repo-url> tank
cd tank
cp .env.example .env             # paste your ANTHROPIC_API_KEY
./scripts/start.sh
# → opens http://localhost:8000
```

What `start.sh` does on first run:

1. Verifies Python 3.11+ is available.
2. Creates `.venv/` and installs dependencies (hash-cached so reruns
   are instant).
3. Checks `ANTHROPIC_API_KEY` is set.
4. Initializes `~/.tank/db.sqlite` (the entire state lives here).
5. Boots uvicorn on `127.0.0.1:8000`.

On subsequent runs it shows a "welcome back" banner with document /
entity / redaction counts.

> ⬜ **Screenshot placeholder**: terminal output of first `./scripts/start.sh`
>
> ![start.sh first run](images/install-first-run-terminal.png)

### Optional knobs in `.env`

```bash
TANK_DB_PATH=                            # default ~/.tank/db.sqlite
TANK_INTERNAL_TLD=acme.internal          # your employer's TLD — gets redacted
TANK_BIND_HOST=127.0.0.1                 # default
TANK_BIND_PORT=8000                      # default
TANK_DIGEST_TIME=08:00                   # morning digest local time
TANK_ENABLE_PERSON_REDACTION=1           # opt-in NER for person names (needs spaCy)
TANK_ENV=prod                            # disables uvicorn --reload — use this on a VM
TANK_TIMEZONE=America/Los_Angeles        # critical on a UTC VM
TANK_API_MAX_RETRIES=4                   # SDK retry budget
TANK_API_TIMEOUT_SECONDS=600             # per-request ceiling
```

---

## Dev VM install (recommended for daily use)

Running Tank on your laptop is fine to try, but it's awkward to keep
it always-on (laptop sleeps, you don't want it spinning when you're
on battery, the journal/digest scheduler only fires while you're
logged in). The recommended pattern: put Tank on a dev VM you own,
and SSH-tunnel to it from your laptop.

### Step 1 — Provision

Whatever VM you have access to is fine: a corporate dev box, a
personal cloud VM, a Tailscale-connected home server. Tank does not
need much:

- 2 vCPU
- 4GB RAM (sentence-transformers model lives ~80MB resident; the
  rest of the headroom is for Python + transient prompt assembly)
- 10GB disk (room for growth over a year)
- Outbound to `api.anthropic.com` (TLS:443)
- Linux with systemd (Ubuntu 22+, Debian 12+, Fedora 38+, RHEL 9+)

### Step 2 — Install

```bash
# On the VM:
ssh you@your-dev-vm

# Install Python 3.11+ if it isn't already.
# Ubuntu/Debian:
sudo apt update && sudo apt install -y python3.12 python3.12-venv git

git clone <repo-url> ~/projects/tank
cd ~/projects/tank
cp .env.example .env
```

Edit `.env` with three additions for VM use:

```bash
ANTHROPIC_API_KEY=sk-ant-...
TANK_ENV=prod                            # never --reload under a supervisor
TANK_TIMEZONE=America/Los_Angeles        # the VM is probably UTC; you are probably not
```

One-shot install:

```bash
./scripts/start.sh        # installs deps, inits DB, prints banner
# Ctrl-C once it's up; we'll run it under systemd next.
```

### Step 3 — systemd

```bash
./scripts/install-systemd.sh
```

The script does:

1. Copies `scripts/tank.service` into `~/.config/systemd/user/tank.service`,
   substituting `%h/projects/tank` for your actual project path.
2. `systemctl --user daemon-reload`.
3. `systemctl --user enable --now tank`.
4. Runs `sudo loginctl enable-linger $USER` so Tank survives SSH
   disconnect.

What the unit configures:

| Setting | Value | Why |
| --- | --- | --- |
| `Type=simple` | foreground uvicorn | matches `start.sh` |
| `Restart=on-failure` | yes | OOM, segfault, unhandled exception → restart |
| `RestartSec=5s` | 5 seconds | back-off before restart |
| `StartLimitBurst=5` / `StartLimitIntervalSec=60` | cap | don't busy-loop on a permanent error |
| `KillSignal=SIGTERM` + `TimeoutStopSec=30` | graceful | the scheduler stop hook gets 30s to drain |
| `Environment=TANK_ENV=prod` | forced | overrides .env if someone forgot |
| `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths=` | sandbox | minimal blast radius if Tank is compromised |

Verify:

```bash
systemctl --user status tank
journalctl --user -u tank -f
curl http://127.0.0.1:8000/healthz
# {"ok": true, "scheduler": "running", "db": "ok", "tenure_day": 0}
```

> ⬜ **Screenshot placeholder**: `systemctl --user status tank`
>
> ![systemd status](images/install-systemd-status.png)

### Step 4 — SSH tunnel from your laptop

Don't bind Tank to `0.0.0.0`. Use an SSH local-forward instead:

```
# ~/.ssh/config on your laptop
Host tank-vm
  HostName your-dev-vm.example.com
  User you
  LocalForward 8000 127.0.0.1:8000
  ServerAliveInterval 60
  ServerAliveCountMax 5
```

Then:

```bash
ssh tank-vm
# leave this terminal parked; open http://localhost:8000 in your browser.
```

The tunnel forwards port 8000 through your SSH session. Nothing else
on the network can reach Tank. When you close the SSH session, the
tunnel drops but Tank keeps running on the VM (systemd holds it).

> ⬜ **Screenshot placeholder**: Tank running in your laptop browser
> via the tunnel.
>
> ![Tank via SSH tunnel](images/install-ssh-tunnel-browser.png)

---

## Verifying the install

After either install, the home page should load and redirect to
`/onboarding` (first run):

```bash
curl -s http://127.0.0.1:8000/healthz | python -m json.tool
# {
#     "ok": true,
#     "scheduler": "running",
#     "db": "ok",
#     "tenure_day": 0
# }
```

Run the privacy assertion to confirm the redaction engine is healthy:

```bash
cd ~/projects/tank
source .venv/bin/activate
python -m pytest -q
# 28 passed
```

---

## Ingesting the sample data

Tank ships with synthetic "Helix Robotics" sample data in `sample_data/`
so you can test all features without exposing real data. First generate
the binary artifacts (PDF, DOCX, PNG) from their markdown sources:

```bash
source .venv/bin/activate
python -m scripts._gen_fixtures             # generate PDF/DOCX/PNG
python -m scripts.load_fixtures --dry-run   # show what would happen
python -m scripts.load_fixtures             # actual ingest — costs ~$5-10
```

After it runs:

```bash
sqlite3 ~/.tank/db.sqlite \
  "SELECT category, COUNT(*) FROM redaction_map GROUP BY category;"
```

You should see counts for `email`, `internal_hostname`,
`aws_account_id`, `secret_token`, `aws_arn`. If any are missing, the
ingest didn't complete.

Then verify nothing leaked:

```bash
python -m scripts.verify_privacy --fixture-pack
# PRIVACY ASSERTION PASSED. No fixture identifiers found in any redacted field.
```

---

## Upgrading

```bash
cd ~/projects/tank
git pull
./scripts/start.sh      # re-runs deps install only if requirements.txt changed
# Under systemd:
systemctl --user restart tank
```

DB schema changes are additive (new tables + new columns via
`_migrate_app_state_columns`). The existing DB is preserved. No
migration step required.

---

## Uninstall

```bash
# Stop the service if it's running.
systemctl --user disable --now tank
rm ~/.config/systemd/user/tank.service
systemctl --user daemon-reload

# Wipe state.
rm -rf ~/.tank/                # deletes db.sqlite + backups + everything

# Wipe the code.
rm -rf ~/projects/tank
```

That's it — Tank doesn't install anything outside `~/.tank/`,
`~/projects/tank/`, and the systemd user unit file.
