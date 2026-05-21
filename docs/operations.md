# Operations — running Tank on a dev VM

You set up Tank on a remote VM with systemd. This doc is what to
do when it doesn't behave.

For first-time install, see [installation.md](installation.md).

---

## Healthcheck

```bash
curl http://127.0.0.1:8000/healthz
```

Returns:

```json
{
    "ok": true,
    "scheduler": "running",
    "db": "ok",
    "tenure_day": 42
}
```

Failure modes:

| Field | Bad value | What it means |
| --- | --- | --- |
| `ok` | `false` | DB couldn't be read on this request. Check disk space, file permissions on `~/.tank/`. |
| `scheduler` | `"stopped"` | The asyncio task isn't running. Usually means an unhandled exception in `_run()` killed it. Restart Tank. |
| `db` | `"error: OperationalError"` etc. | SQLite blew up. Common causes: disk full, NFS mount issues, corruption. |

Wire into systemd:

```
# scripts/tank.service already includes:
ExecStartPost=/bin/sleep 5
# or use an external probe — there's no Type=notify support yet.
```

For more invasive monitoring (Prometheus / Datadog / etc.):
healthz is the only endpoint that doesn't touch Sonnet or load the
embedder, so it's safe to scrape at 10s cadence.

---

## Logs

systemd captures uvicorn stdout + stderr into journald:

```bash
journalctl --user -u tank -f             # tail
journalctl --user -u tank --since today  # today's logs
journalctl --user -u tank -p warning     # only warnings + errors
```

Loggers Tank uses:

| Logger | What it covers |
| --- | --- |
| `tank.main` | Startup / shutdown |
| `tank.scheduler` | Cron tick + fired jobs |
| `tank.nudges` | Nudge gate firings |
| `tank.reports` | Report generation outcomes + Sonnet failures |
| `tank.event_bus` | SSE queue full warnings |
| `tank.threat_modeling` | TM generation |
| `tank.decisions` | Decision extraction from docs |
| `tank.compliance` | Evidence collection |
| `tank.iam_translator` | IAM explain failures |
| `tank.lessons` | Lesson extraction |
| `tank.glossary` | Glossary discover |
| `tank.philosophy` | Philosophy seed/evolve |

Set `PYTHONUNBUFFERED=1` (already in the systemd unit) so logs flow
in real time.

---

## Backups

The scheduler fires `_fire_weekly_backup()` every Sunday at 03:00.

### Where backups live

`~/.tank/backups/db-YYYY-MM-DD.sqlite`

### How they're made

`sqlite3.Connection.backup()` via the live `_CONN`. WAL-safe; doesn't
require a checkpoint pause; no service interruption.

### Retention

Keeps the last 8 weekly snapshots. The retention sweep runs after
every backup — older files are unlinked and their `backup_log` rows
deleted.

### Manually triggering one

```python
# In the venv:
python -c "from app.claude.scheduler import _take_backup; _take_backup()"
```

Or via the API if you wire it later (no endpoint by default).

### Inspecting the ledger

```bash
sqlite3 ~/.tank/db.sqlite \
  "SELECT path, size_bytes, datetime(created_at,'unixepoch','localtime'), status
   FROM backup_log
   ORDER BY created_at DESC;"
```

### Restoring

```bash
# Stop the service.
systemctl --user stop tank

# Replace the live DB with a backup.
cp ~/.tank/backups/db-2026-05-12.sqlite ~/.tank/db.sqlite
rm -f ~/.tank/db.sqlite-wal ~/.tank/db.sqlite-shm

# Restart.
systemctl --user start tank
```

The next request reinitializes any missing tables (idempotent
schema). Your KB, decisions, threat models, lessons, and philosophy
doc are all back as of the backup date.

> ⬜ **Screenshot placeholder**: backup directory listing.
>
> ![Backups](images/ops-backups.png)

---

## The scheduler

Single asyncio.Task started in `app/main.py::lifespan` and cancelled
on shutdown. Wakes every 60s.

### Job table

| Job | When | What it does |
| --- | --- | --- |
| `digest` | daily, at `app_state.digest_time` | Regenerate nudges (rate-limited 2/day), run due `report_subscriptions`, check anniversary milestone |
| `reflection` | weekly, `reflection_day` 16:00 | Weekly reflection trigger (UI-driven from here) |
| `journal_prompt` | weekday 18:00 if no entry today | Insert `journal_prompt` nudge |
| `auto_briefs` | nightly 22:00 | Generate meeting_prep for tomorrow's ICS meetings (≤5/day) |
| `attack_surface_snapshot` | Sunday 09:00 | Snapshot all Endpoint entities + diff vs prior |
| `weekly_backup` | Sunday 03:00 | `sqlite3.Connection.backup()` to `~/.tank/backups/`; keep 8 |

### Why jobs might not fire

Each tick checks `scheduler_state_store.has_fired(job, label)`.
Labels:

- Daily jobs: `YYYY-MM-DD` (local).
- Weekly jobs: `YYYY-Www` (ISO week).

If a job hasn't fired for today/this-week, it runs. If it has,
skipped. Inspect state:

```bash
sqlite3 ~/.tank/db.sqlite \
  "SELECT job_name, last_label,
          datetime(last_fired_at,'unixepoch','localtime')
   FROM scheduler_state ORDER BY job_name;"
```

Common reasons a job didn't fire today:

- Tank wasn't running when its trigger time passed.
- The trigger time is in a different timezone than you expect. Set
  `TANK_TIMEZONE=America/Los_Angeles` (or your IANA TZ).
- The Sonnet call inside the job failed and threw — check logs.
  Scheduler state is marked *before* the work runs, so a failed
  job doesn't re-fire on the next tick. Manual retrigger needed.

### Manually re-firing a job

```python
# Drop the last-fired marker, then the next tick (within 60s) re-fires.
python -c "
from app.db import get_conn, LOCK
with LOCK:
    get_conn().execute('DELETE FROM scheduler_state WHERE job_name = ?',
                       ('digest',))
"
```

---

## Time zones

The scheduler uses `TANK_TIMEZONE` if set, else local time.

```bash
# Inside the venv:
python -c "
import os; os.environ['TANK_TIMEZONE'] = 'America/Los_Angeles'
from app.claude.scheduler import _now
print(_now())
"
```

Hosted VMs are almost always UTC. **Almost everyone forgets this**
and is surprised when the 08:00 digest fires at midnight their time.

To change after install:

```bash
echo 'TANK_TIMEZONE=America/Los_Angeles' >> ~/projects/tank/.env
systemctl --user restart tank
```

---

## Disk usage

After a year of moderate use expect:

| Path | Size |
| --- | --- |
| `~/.tank/db.sqlite` | 100MB-2GB depending on ingest volume |
| `~/.tank/db.sqlite-wal` | up to ~50MB between checkpoints |
| `~/.tank/backups/` | 8× recent db.sqlite size |
| `~/projects/tank/.venv/` | ~500MB (Python + sentence-transformers) |

To check:

```bash
du -sh ~/.tank/ ~/projects/tank/.venv/
```

If `~/.tank/` is growing fast, the most common culprits:

- **Massive ingest** — a 10GB repo without `.gitignore` discipline.
  Add a `.tankignore` (TODO: not currently honored — for now,
  pre-filter before ingest).
- **High-frequency chat** — `messages` and `chunks_fts` grow.
- **Unbounded `usage_events`** — every view/click writes one. Trim
  with `DELETE FROM usage_events WHERE created_at < strftime('%s','now')-7776000`
  (90d retention is reasonable).

### WAL truncation

SQLite auto-checkpoints at 1000 pages. To force one:

```bash
sqlite3 ~/.tank/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
```

---

## Connectivity issues

Tank only needs **`api.anthropic.com:443`** outbound by default.

If chat / report generation is failing:

1. Check the API key:
   ```bash
   curl -H "x-api-key: $ANTHROPIC_API_KEY" \
        https://api.anthropic.com/v1/models \
        | python -m json.tool
   ```
2. Look at retry logs. Tank uses `max_retries=4` on the SDK; you'll
   see retry attempts in `journalctl` before final failure.
3. Tune `TANK_API_TIMEOUT_SECONDS` if you're behind a slow proxy.

If you've configured optional connectors (CVE feed, GitHub poller),
the corresponding URLs must also be reachable.

---

## Process supervision quirks

### Tank restarted at 08:05; did the digest fire twice?

No — scheduler state is durable. After Phase-Ops, `_LAST_FIRED` lives
in the `scheduler_state` table, so a restart between 08:00 and the
first post-restart tick doesn't re-fire. (Pre-ops it would have.)

### Tank crashed and systemd restarted it 6 times in a minute — now nothing.

The unit has `StartLimitBurst=5 StartLimitIntervalSec=60`. After 5
restarts in 60s, systemd stops trying. Reset:

```bash
systemctl --user reset-failed tank
systemctl --user start tank
```

But first read the logs for the underlying error.

### Mid-stream chat got interrupted by a restart.

The user message is persisted (commit happens before the assistant
turn kicks off as a background task). The assistant response is
lost — there's no resume. The user has to resend.

Future: track in-flight tasks and persist a "turn in progress"
marker. Out of scope for now.

### How do I gracefully shutdown for a planned maintenance?

```bash
systemctl --user stop tank
# Or:
kill -TERM <uvicorn pid>
```

The lifespan handler stops the scheduler. The unit gives uvicorn 30s
(`TimeoutStopSec=30`) to drain before SIGKILL.

---

## Upgrading Tank

```bash
cd ~/projects/tank
git pull
./scripts/start.sh           # re-installs deps only if requirements.txt changed
# Under systemd:
systemctl --user restart tank
```

Schema migrations are additive — no manual migration step.

---

## Sanity checklist after install

- [ ] `curl http://127.0.0.1:8000/healthz` returns `ok=true, scheduler=running, db=ok`
- [ ] `journalctl --user -u tank -f` shows "scheduler started"
- [ ] `python -m pytest -q` (in the venv) → 28/28 pass
- [ ] `python -m scripts.verify_privacy --fixture-pack` → PASSED (after fixture ingest)
- [ ] `~/.ssh/config` has a `Host tank-vm` entry with `LocalForward 8000 127.0.0.1:8000`
- [ ] `.env` has `TANK_ENV=prod` AND `TANK_TIMEZONE=<your TZ>`
- [ ] `loginctl show-user $USER | grep Linger` shows `Linger=yes`
