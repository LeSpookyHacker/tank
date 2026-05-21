# Troubleshooting

Known issues, common errors, and how to fix them. Organized roughly
by where they show up.

---

## Install / first boot

### `start.sh` exits with "python3 not found"

You don't have Python on PATH. Install 3.11+:

- **Ubuntu / Debian**: `sudo apt install -y python3.12 python3.12-venv`
- **Fedora / RHEL**: `sudo dnf install -y python3.12`
- **macOS (Homebrew)**: `brew install python@3.12`

Verify: `python3 --version` → `3.11.x` or higher.

### `start.sh` exits with "Python 3.9 found, need 3.11+"

macOS ships 3.9 as `/usr/bin/python3`. That's the system Python.
Get a real one: `brew install python@3.12`, then run `start.sh`
from a fresh shell so the new `python3` is on PATH.

(Tank does technically run on 3.9 thanks to `eval_type_backport` —
but `sqlite-vec` won't load and you'll lose vector search.)

### `start.sh` exits with "ANTHROPIC_API_KEY is empty"

You either didn't create `.env` or didn't paste the key. From the
project root:

```bash
cp .env.example .env
# Then edit .env and add a real key from
# https://console.anthropic.com/settings/keys
```

### "Permission denied" on `~/.tank/`

The directory's ownership is wrong. Most often because you ran
`./scripts/start.sh` once as root and once as your normal user.

```bash
sudo chown -R $USER:$USER ~/.tank
```

### "sqlite-vec extension load failed" in the logs

System Python doesn't have `enable_load_extension`. Tank still
works — FTS5 keyword search is enabled, vector search falls back.
To get true vector retrieval, install Python from Homebrew or
python.org.

You can verify the fallback is OK by chatting:

> "find me everything about authentication"

Should still return reasonable hits.

---

## systemd / running on a VM

### `systemctl --user status tank` shows `failed`

Look at the logs:

```bash
journalctl --user -u tank -n 50
```

Most common causes:

- **Working directory wrong** in the unit file — the install script
  substitutes `%h/projects/tank` for the actual path, but if you
  moved the repo, edit `~/.config/systemd/user/tank.service` and
  re-run `systemctl --user daemon-reload && systemctl --user restart tank`.
- **`.env` missing or unreadable** — `EnvironmentFile=` path in the
  unit must exist and be readable by the user.
- **Anthropic API key invalid** — Tank starts but the first request
  fails. Verify with `curl` (see [faq.md § Cost](faq.md#cost)).

### Tank exits 5 times in 60s then stops

The unit has `StartLimitBurst=5 StartLimitIntervalSec=60`. Reset:

```bash
systemctl --user reset-failed tank
journalctl --user -u tank -p err   # find the root cause first!
systemctl --user start tank
```

### Tank dies as soon as I close my SSH session

You didn't enable linger. Fix:

```bash
sudo loginctl enable-linger $USER
systemctl --user restart tank
```

`linger=yes` means user services stay running even when no session
is active. Verify: `loginctl show-user $USER | grep Linger` →
`Linger=yes`.

### My laptop browser shows "connection refused" via the SSH tunnel

Three things to check:

1. **Tunnel actually open?** `lsof -i :8000` on your laptop should
   show ssh listening.
2. **Tank running on the VM?** SSH in and `curl localhost:8000/healthz`.
3. **`ServerAliveInterval` set?** Long-idle SSH tunnels die. Add
   `ServerAliveInterval 60` and `ServerAliveCountMax 5` to your
   `~/.ssh/config` for the `tank-vm` host.

### Tank's working but pages look unstyled / no purple

The Nyx theme loads Inter + JetBrains Mono from `fonts.googleapis.com`.
On a locked-down VM with restricted outbound, the fonts won't load
and the UI falls back to system fonts. Tank still works, just looks
plainer.

Options:
- Whitelist `fonts.googleapis.com` and `fonts.gstatic.com` in your
  egress policy.
- Self-host the fonts: download Inter + JetBrains Mono variable
  fonts, drop them in `app/static/fonts/`, and edit
  `app/templates/base.html` to reference them locally instead.

---

## Chat

### Chat just spins; no streaming output

Possibilities, in order:

1. **No API key / invalid key** — `journalctl --user -u tank -f`
   will show `AuthenticationError`.
2. **Anthropic API outage / 5xx** — Tank retries 4× with backoff,
   then the SSE `done` event carries `kind="error"`. Check
   [status.anthropic.com](https://status.anthropic.com).
3. **SSE connection dropped silently** — restart the page (Cmd-R).
   The `idle_timeout=15s` heartbeat usually prevents this.
4. **Embedder model still downloading on first chat turn** — first
   chat after install pulls `sentence-transformers/all-MiniLM-L6-v2`
   (~80MB) from HuggingFace. Wait 30-60s.

### Chat reply has no citations

Tank's chat tools may have returned nothing — i.e., the question
genuinely doesn't match anything in your KB. Tank is supposed to
say "I don't know" in that case. If it's still inventing things
without citations, click "This was wrong" and the correction goes
into notes.

If this happens **consistently** for questions that should match,
your retrieval is broken — most likely sqlite-vec isn't loaded and
FTS5 alone is missing semantic matches. Check the install section
above.

### "This was wrong" doesn't seem to do anything

It creates a `notes` row with `provenance='user'` and the
disputed-entity-attr metadata. Tank doesn't immediately re-train
or anything — the correction shows up the next time relevant
chunks are retrieved (because the note becomes a chunk too).

---

## Ingestion

### Ingest of a folder/repo silently produces 0 entities

Usually one of:

1. **Document(s) already ingested** — Tank dedupes by sha256.
   Check `documents` table for the source path.
2. **Parser didn't recognize the file** — extensions not in
   `app/ingest/parsers/__init__.py::_BY_EXT` get rejected with
   "no parser for extension X". Add the extension if it should be
   supported.
3. **Sonnet entity extractor returned empty** — the doc was
   technical but didn't mention any nameable entities. Normal.
4. **API call failed silently** — `journalctl --user -u tank -f`
   during ingest will show the error if Sonnet rejected the call.

### Ingest of a PDF is mostly empty

The PDF parser uses `pypdf` for text extraction. If a page has
< 50 chars (i.e., it's an image-only scan), it gets skipped with a
log message. To pick those up, manually run the page through the
image parser (or wait for a Phase 16 OCR routing).

### Repo ingest takes forever

Repo summarization is the biggest single API call in Tank (one
Sonnet call over the structured `RepoSummary`). Big repos with
many manifests + workflows can take 30-60s. If it's longer than
that, look at the logs — usually it's stuck on a `tiktoken` import
on first call (one-time cost) or the Sonnet call is being retried
silently.

---

## Reports & artifacts

### Report generation says "no output"

Three causes:

1. **Adaptive thinking timed out** — bump `TANK_API_TIMEOUT_SECONDS`
   in `.env` (default 600s; can go to 1200).
2. **Schema validation failed** — Sonnet returned text that didn't
   parse as the Pydantic model. Logs will show the validation
   error. Usually a prompt issue if it's reproducible. File an
   issue with the prompt + sample output.
3. **No relevant context** — the scope block has nothing in it.
   E.g., generating a `threat_landscape` for a Service that has no
   linked chunks. Ingest more docs about that service first.

### Threat model regenerate says "drift" but the arch hasn't changed

`arch_snapshot_hash` is computed over the *set* of chunks attached
to the service (direct entity_chunks links + 1-hop neighbor chunks).
If you re-ingested a related doc, the set changes even if the
content didn't.

Workaround: regenerate. The new TM should mark every prior threat
`still_valid` and have `new = []`. Confirm the TM.

### "I own this" doesn't appear

The button is only on `Service` entity pages. For other entity
types, claim via the API:

```bash
curl -X POST http://localhost:8000/api/me/owned \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "<id>", "role": "owner"}'
```

---

## Scheduler

### My morning digest fires at midnight

You're in a different timezone than the VM. Set `TANK_TIMEZONE`
in `.env`:

```bash
echo 'TANK_TIMEZONE=America/Los_Angeles' >> ~/projects/tank/.env
systemctl --user restart tank
```

Verify:

```bash
sqlite3 ~/.tank/db.sqlite \
  "SELECT job_name, last_label,
          datetime(last_fired_at,'unixepoch','localtime')
   FROM scheduler_state ORDER BY job_name;"
```

### A scheduler job didn't fire today

Inspect:

```bash
sqlite3 ~/.tank/db.sqlite \
  "SELECT * FROM scheduler_state ORDER BY job_name;"
```

If the job's row is missing or has a `last_label` older than today,
Tank was either:

- Not running when the trigger time passed.
- Threw an exception inside the job body. Check
  `journalctl --user -u tank --since today` for `WARNING` or
  `ERROR`.

Manual retrigger:

```bash
sqlite3 ~/.tank/db.sqlite \
  "DELETE FROM scheduler_state WHERE job_name = 'digest';"
# next tick (within 60s) re-fires.
```

### Backups aren't appearing

Check the ledger:

```bash
sqlite3 ~/.tank/db.sqlite \
  "SELECT path, datetime(created_at,'unixepoch','localtime'), status
   FROM backup_log ORDER BY created_at DESC LIMIT 8;"
```

If empty, the Sunday 03:00 job hasn't fired yet (Tank just installed?
Sunday hasn't happened?). Manually trigger:

```bash
source .venv/bin/activate
python -c "from app.claude.scheduler import _take_backup; _take_backup()"
ls -la ~/.tank/backups/
```

### Tank scheduler `is_running()` returns false

The asyncio task crashed. Restart:

```bash
systemctl --user restart tank
```

The lifespan re-creates the task on boot. Investigate the crash via
logs.

---

## DB / storage

### "database is locked"

You have two processes both writing to `~/.tank/db.sqlite`. Tank
assumes single-process. If you also have a `python -m scripts.ingest_cli`
running while the FastAPI app is up, you can hit this.

Workarounds:

- Stop one of them.
- Use the API (`POST /api/ingest/path`) instead of the CLI.

### "no such table: foo" after an upgrade

The DB schema migration runs on first `get_conn()` call, which
happens during FastAPI's lifespan. If Tank crashes before lifespan
finishes, the schema doesn't get updated.

Manual fix:

```bash
source .venv/bin/activate
python -c "from app.db import get_conn; get_conn(); print('schema ok')"
```

This pings the DB and triggers the `_init_schema` run.

### Wiping the DB doesn't seem to wipe everything

The wipe endpoint deletes `~/.tank/db.sqlite` and its WAL/SHM
sidecars but **not** the `~/.tank/backups/` directory. Intentional —
backups are your escape hatch. To wipe truly:

```bash
rm -rf ~/.tank/
systemctl --user restart tank
```

---

## Privacy verification

### `verify_privacy.py --fixture-pack` fails

This is **the** important alert. Something leaked. Don't ignore.

```bash
python -m scripts.verify_privacy --fixture-pack
# FAIL  'AKIAIOSFODNN7EXAMPLE' found in 1 redacted field(s):
#   - chunks.text_redacted (id=abcdef…)
```

Steps:

1. **Stop using Tank with real data immediately.**
2. Look at the offending chunk: `SELECT text_redacted FROM chunks WHERE id = 'abcdef'`.
3. Identify the redaction rule that should have matched the leaked
   identifier. Check it's enabled (Settings → Redaction).
4. File a bug. Include the exact leaked value, the chunk text,
   which file it came from.

This has not happened in test runs against the fixture corpus —
but it's the failure mode the script exists to catch.

### `verify_privacy.py` says "no DB" but I have one

`TANK_DB_PATH` differs between your `.env` and your invocation.
Pass it explicitly:

```bash
python -m scripts.verify_privacy --db ~/.tank/db.sqlite --fixture-pack
```

---

## Filing a bug

If you hit something not covered here:

1. Capture the logs: `journalctl --user -u tank --since "1 hour ago" > /tmp/tank.log`
2. Note the version: `git -C ~/projects/tank rev-parse HEAD`
3. Note your platform: `uname -a && python3 --version`
4. Redact anything personal from the log before sharing.
5. Open an issue with the above + a description of what you were
   doing.
