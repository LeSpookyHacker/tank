"""Background scheduler for partner-mode behaviors.

A single asyncio.Task owns the cron-ish loop. It wakes every 60s,
checks what needs to run, and dispatches:

- Daily digest time (per `app_state.digest_time`): regenerate nudges,
  dispatch due report subscriptions, check for anniversary milestones.
- Friday 16:00 (per `app_state.reflection_day`): weekly reflection.
- Weekdays 18:00: journal prompt (if no entry today).
- Nightly 22:00: pre-meeting briefs for tomorrow.
- Sunday 09:00: attack-surface snapshot.
- Sunday 03:00: SQLite backup with N-week retention.

Last-fired markers are persisted to the `scheduler_state` table so
that a restart (intentional or via systemd Restart=on-failure) does
not double-fire same-day jobs or skip jobs not yet fired today.

Time zone: defaults to the VM's local time. Set `TANK_TIMEZONE`
(e.g. "America/Los_Angeles") in .env to override — recommended on
hosted VMs that run in UTC.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo  # py3.9+
except ImportError:                # pragma: no cover
    ZoneInfo = None                # type: ignore

from app.claude.event_bus import publish
from app.role import get_state, tenure_day
from app.storage import scheduler_state_store

log = logging.getLogger("tank.scheduler")

_TASK: asyncio.Task | None = None

# Wake interval. Every clock-time job below is gated by `hhmm >= "HH:MM"`,
# so as long as we wake at least once per minute we won't miss a window.
_TICK_INTERVAL_SECONDS = 60

# ── Schedule (single source of truth for clock literals) ──
#
# Each entry is (idempotency-key, fire-after time, label-granularity). The
# `_tick` dispatcher reads `_now()`, compares the wall clock, and asks
# `scheduler_state_store.has_fired(key, label)` before firing. Labels are
# daily for daily jobs, ISO-week for weekly jobs — so a Sunday-only job
# fires at most once per ISO week even if we restart mid-Sunday.
#
# `digest_time` is user-configurable in app_state; the rest are fixed.
_REFLECTION_TIME = "16:00"   # Friday afternoon — end-of-week ritual.
_JOURNAL_TIME    = "18:00"   # Weekday evening — after work hours.
_AUTO_BRIEFS_TIME = "22:00"  # Night before — meetings on tomorrow's calendar.
_BACKUP_TIME     = "03:00"   # Sunday small hours — minimal write activity.
_ATTACK_SURFACE_TIME = "09:00"  # Sunday morning — fresh week diff.
_SEC_PROGRAM_TIME    = "09:30"  # Sunday morning — right after attack-surface.

# Tenure-day milestones that fire an anniversary retro. The ordering here
# also drives the philosophy-doc lifecycle: Day-30 seeds, the rest evolve.
_ANNIVERSARIES = {30, 60, 90, 180, 365}

# Cap auto-generated meeting briefs per night so a busy calendar doesn't
# burn through the daily token budget.
_AUTO_BRIEFS_MAX_PER_NIGHT = 5

# How far ahead `_fire_auto_briefs` looks for meetings (in seconds).
_AUTO_BRIEFS_LOOKAHEAD_START = 4 * 3600    # skip anything in the next 4h
_AUTO_BRIEFS_LOOKAHEAD_END   = 36 * 3600   # up to ~tomorrow EOD

# Weekly backup retention: keep the last N snapshots; older ones are unlinked.
_BACKUP_RETAIN_N = 8


def _now() -> datetime:
    """Local-aware datetime using TANK_TIMEZONE if set, else system tz."""
    tz_name = os.environ.get("TANK_TIMEZONE", "").strip()
    if tz_name and ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            log.warning("invalid TANK_TIMEZONE=%r; falling back to local", tz_name)
    return datetime.now()


def _today_label(dt: datetime | None = None) -> str:
    """Idempotency key for daily jobs: YYYY-MM-DD in scheduler-local tz."""
    return (dt or _now()).strftime("%Y-%m-%d")


def _week_label(dt: datetime | None = None) -> str:
    """Idempotency key for weekly jobs: ISO-week label (e.g. `2026-W22`).

    Using ISO weeks means a Sunday-only job remains de-duplicated even if
    the process restarts later that same Sunday.
    """
    d = dt or _now()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def start() -> None:
    """Start the scheduler task. Called once from `app.main.lifespan`."""
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    _TASK = asyncio.create_task(_run(), name="tank-scheduler")
    log.info("scheduler started")


def stop() -> None:
    """Cancel the scheduler task. Called from `app.main.lifespan` on shutdown."""
    global _TASK
    if _TASK is not None:
        _TASK.cancel()
        _TASK = None
        log.info("scheduler stopped")


def is_running() -> bool:
    """Healthcheck hook — `/healthz` reports this."""
    return _TASK is not None and not _TASK.done()


async def _run() -> None:
    """Main loop. Catches per-tick exceptions so one bad job can't kill the loop."""
    try:
        while True:
            try:
                await _tick()
            except Exception as exc:
                log.exception("scheduler tick failed: %s", exc)
            await asyncio.sleep(_TICK_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        log.info("scheduler cancelled")
        raise


async def _tick() -> None:
    """Single dispatch pass. Each branch is guarded by `has_fired()` so
    same-day reruns across restarts are safe — durability lives in the
    `scheduler_state` table, not in process memory."""
    now = _now()
    today_label = _today_label(now)
    week_label = _week_label(now)
    hhmm = now.strftime("%H:%M")
    weekday_short = now.strftime("%a").lower()[:3]
    state = get_state()

    # ── Daily digest (user-configurable time) ──
    # Regenerates nudges, fires due report subscriptions, checks anniversaries.
    if hhmm >= state.digest_time and \
            not scheduler_state_store.has_fired("digest", today_label):
        await _fire_digest(today_label)

    # ── Weekly reflection (user-configurable day, fixed 16:00) ──
    if weekday_short == state.reflection_day.lower()[:3] \
            and hhmm >= _REFLECTION_TIME \
            and not scheduler_state_store.has_fired("reflection", today_label):
        await _fire_reflection(today_label)

    # ── Weekday journal prompt (Mon–Fri at 18:00) ──
    # `weekday() < 5` is Monday–Friday in Python's ISO numbering.
    if now.weekday() < 5 and hhmm >= _JOURNAL_TIME \
            and not scheduler_state_store.has_fired("journal_prompt", today_label):
        await _fire_journal_prompt(today_label)

    # ── Nightly auto-briefs for tomorrow's meetings (22:00) ──
    if hhmm >= _AUTO_BRIEFS_TIME \
            and not scheduler_state_store.has_fired("auto_briefs", today_label):
        await _fire_auto_briefs(today_label)

    # ── Sunday attack-surface snapshot (09:00) ──
    if weekday_short == "sun" and hhmm >= _ATTACK_SURFACE_TIME \
            and not scheduler_state_store.has_fired(
                "attack_surface_snapshot", week_label):
        await _fire_attack_surface_snapshot(week_label)

    # ── Sunday security-program metrics snapshot (09:30) ──
    if weekday_short == "sun" and hhmm >= _SEC_PROGRAM_TIME \
            and not scheduler_state_store.has_fired(
                "security_program_snapshot", week_label):
        await _fire_security_program_snapshot(week_label)

    # ── Sunday SQLite backup (03:00, while write traffic is minimal) ──
    if weekday_short == "sun" and hhmm >= _BACKUP_TIME \
            and not scheduler_state_store.has_fired(
                "weekly_backup", week_label):
        await _fire_weekly_backup(week_label)

    # ── Anthropic Message Batches poll ──
    # Cheap when nothing is in-flight (one SELECT). When a background
    # batch (auto_briefs, subscriptions, etc.) finishes, its results are
    # fetched here and handed to the registered handler for persistence.
    # Runs every tick so latency-from-batch-end to result-processing is
    # at most one tick (~60s).
    try:
        from app.claude import batches as batches_mod
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, batches_mod.poll_inflight)
    except Exception as exc:
        log.warning("batches poll failed: %s", exc)


# ---------------- job bodies ----------------

async def _fire_digest(today_label: str) -> None:
    """Daily digest tick: regenerate nudges, run due subscriptions, anniversary check.

    Each sub-task is wrapped so a failure in one (e.g. anniversary) doesn't
    skip the next (subscriptions). `mark_fired` runs first so a crash in
    one sub-task can't trigger a same-day re-fire.
    """
    scheduler_state_store.mark_fired("digest", today_label)
    log.info("digest firing for %s", today_label)
    publish("scheduler.global", "digest_fired", {"date": today_label})

    # Nudges and subscriptions call Sonnet → must run in an executor so the
    # blocking SDK call doesn't stall the scheduler loop.
    try:
        from app.claude import nudges as nudges_mod
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, nudges_mod.generate_nudges)
    except Exception as exc:
        log.warning("nudge generation failed: %s", exc)

    try:
        await _run_due_subscriptions()
    except Exception as exc:
        log.warning("subscription run failed: %s", exc)

    try:
        await _maybe_anniversary()
    except Exception as exc:
        log.warning("anniversary check failed: %s", exc)


async def _fire_reflection(today_label: str) -> None:
    """Weekly reflection: emit an event; the UI surfaces the prompt elsewhere.

    Intentionally light — we don't call Sonnet here. The downstream consumer
    (reflection page) reads journal entries on demand.
    """
    scheduler_state_store.mark_fired("reflection", today_label)
    log.info("weekly reflection firing for %s", today_label)
    publish("scheduler.global", "reflection_due", {"date": today_label})


async def _fire_journal_prompt(today_label: str) -> None:
    """Insert a journal nudge if the user hasn't already written one today."""
    scheduler_state_store.mark_fired("journal_prompt", today_label)
    from app.storage import journal_store, nudges_store
    today = journal_store.get_today()
    if today:
        return
    log.info("journal-prompt nudge for %s", today_label)
    nudges_store.insert(
        kind="journal_prompt",
        title="One-line journal for today?",
        body="What changed today? Even one sentence keeps the KB fresh.",
        priority=35,
    )
    publish("scheduler.global", "journal_prompt", {"date": today_label})


async def _fire_auto_briefs(today_label: str) -> None:
    """Generate meeting-prep briefs for tomorrow's calendar items.

    Lookahead window is 4h–36h: skips anything imminent (no time to act on
    a brief) and stops around tomorrow's EOD. Capped at
    `_AUTO_BRIEFS_MAX_PER_NIGHT` to bound token spend on busy calendars.
    """
    scheduler_state_store.mark_fired("auto_briefs", today_label)
    try:
        from app.storage import meetings_store
    except Exception:
        return
    from app.claude import meeting_prep as mp_mod

    start = time.time() + _AUTO_BRIEFS_LOOKAHEAD_START
    end = time.time() + _AUTO_BRIEFS_LOOKAHEAD_END
    upcoming = meetings_store.list_between(start, end) \
        if hasattr(meetings_store, "list_between") else []
    loop = asyncio.get_event_loop()
    generated = 0
    for m in upcoming:
        if generated >= _AUTO_BRIEFS_MAX_PER_NIGHT:
            break
        attendees = m.get("attendees") or []
        if not attendees:
            continue
        who = attendees[0]
        try:
            await loop.run_in_executor(
                None, mp_mod.prepare, who, m.get("title"), None,
            )
            generated += 1
        except Exception as exc:
            log.warning("auto-brief for %r failed: %s", who, exc)
    if generated:
        publish("scheduler.global", "auto_briefs_fired",
                {"count": generated, "date": today_label})


async def _fire_attack_surface_snapshot(week_label: str) -> None:
    """Weekly attack-surface snapshot. Diff against the prior week is what
    the UI surfaces — see `app/claude/attack_surface.py`."""
    scheduler_state_store.mark_fired("attack_surface_snapshot", week_label)
    try:
        from app.claude.attack_surface import snapshot
    except Exception:
        return
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, snapshot)
        publish("scheduler.global", "attack_surface_snapshot",
                {"week": week_label})
    except Exception as exc:
        log.warning("attack-surface snapshot failed: %s", exc)


async def _fire_security_program_snapshot(week_label: str) -> None:
    """Weekly counters snapshot (open risks, vuln age, TM drift, etc.).

    Persisted to `security_program_snapshots`; the dashboard diffs the
    latest two to show week-over-week deltas.
    """
    scheduler_state_store.mark_fired("security_program_snapshot", week_label)
    loop = asyncio.get_event_loop()
    try:
        from app.routers.security_program import take_snapshot
        sid = await loop.run_in_executor(None, take_snapshot)
        publish("scheduler.global", "security_program_snapshot",
                {"week": week_label, "snapshot_id": sid})
    except Exception as exc:
        log.warning("security-program snapshot failed: %s", exc)


async def _fire_weekly_backup(week_label: str) -> None:
    """Trigger the online SQLite backup. Retention enforced inside `_take_backup`."""
    scheduler_state_store.mark_fired("weekly_backup", week_label)
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _take_backup)
        publish("scheduler.global", "weekly_backup", {"week": week_label})
    except Exception as exc:
        log.warning("weekly backup failed: %s", exc)


def _take_backup() -> None:
    """Online `sqlite3.Connection.backup()` to `~/.tank/backups/db-YYYY-MM-DD.sqlite`.

    Safe to run concurrently with writes because the source DB is in WAL
    mode — `.backup()` walks pages without blocking writers. Runs inside
    the scheduler's executor so it doesn't stall the event loop.
    """
    import sqlite3
    from pathlib import Path

    from app.db import db_path, get_conn
    from app.storage import backup_log_store

    src = db_path()
    if not src.exists():
        return
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    label = _today_label()
    dst = backup_dir / f"db-{label}.sqlite"

    # Use the live conn as the source — .backup() is online-safe under WAL.
    src_conn = get_conn()
    dst_conn = sqlite3.connect(dst)
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        dst_conn.close()

    size = dst.stat().st_size if dst.exists() else 0
    backup_log_store.record(dst, size)
    log.info("backup written: %s (%d bytes)", dst, size)

    # Retention: drop anything beyond the most recent `_BACKUP_RETAIN_N`.
    for stale in backup_log_store.stale(keep_n=_BACKUP_RETAIN_N):
        p = Path(stale["path"])
        if p.exists():
            try:
                p.unlink()
            except OSError as exc:
                log.warning("could not unlink %s: %s", p, exc)
        backup_log_store.delete_record(stale["id"])


async def _run_due_subscriptions() -> None:
    """Fire every report subscription whose `next_run_at` has passed.

    Looks up the generator in REPORT_REGISTRY. Scope-bearing report kinds
    (threat_landscape, questions_for_team) require the scope JSON to carry
    the relevant target (service_id, team_or_person); skip if missing.
    """
    from app.claude.reports import REPORT_REGISTRY
    from app.storage import subscriptions_store
    loop = asyncio.get_event_loop()
    for sub in subscriptions_store.list_due_for_run():
        gen = REPORT_REGISTRY.get(sub["kind"])
        if gen is None:
            continue
        try:
            import json
            scope = json.loads(sub["scope_json"] or "{}")
            if sub["kind"] == "threat_landscape":
                if not scope.get("service_id"):
                    continue
                report_id = await loop.run_in_executor(
                    None, gen, scope["service_id"],
                )
            elif sub["kind"] == "questions_for_team":
                if not scope.get("team_or_person"):
                    continue
                report_id = await loop.run_in_executor(
                    None, gen, scope["team_or_person"],
                )
            else:
                report_id = await loop.run_in_executor(None, gen)
            subscriptions_store.mark_run(sub["id"], report_id)
            publish("reports.global", "subscription_run",
                    {"subscription_id": sub["id"],
                     "report_id": report_id, "kind": sub["kind"]})
        except Exception as exc:
            log.warning("subscription %s failed: %s", sub["id"], exc)


async def _maybe_anniversary() -> None:
    """Fire anniversary retros on tenure-day milestones.

    Three artifacts ship per milestone: a generic retro, a security-focused
    retro, and a philosophy doc (seeded at Day-30, evolved thereafter).
    De-duped via `reports_store.latest_for_kind` so a same-day retrigger
    can't double-write.
    """
    state = get_state()
    if not state.tenure_started_at:
        return
    day = tenure_day()
    if day not in _ANNIVERSARIES:
        return
    from app.storage import reports_store
    if reports_store.latest_for_kind(f"anniversary_{day}"):
        return
    log.info("firing Day-%d anniversary retro", day)
    from app.claude.anniversary import generate as anniv_generate
    loop = asyncio.get_event_loop()
    try:
        report_id = await loop.run_in_executor(None, anniv_generate, day)
        publish("scheduler.global", "anniversary_fired",
                {"day_n": day, "report_id": report_id})
    except Exception as exc:
        log.warning("anniversary day %d failed: %s", day, exc)

    try:
        from app.claude.anniversary_security import generate as sec_generate
        sec_report_id = await loop.run_in_executor(None, sec_generate, day)
        publish("scheduler.global", "anniversary_security_fired",
                {"day_n": day, "report_id": sec_report_id})
    except Exception as exc:
        log.warning("anniversary_security day %d failed: %s", day, exc)

    if day == 30:
        try:
            from app.claude.philosophy import seed as philosophy_seed
            phil_id = await loop.run_in_executor(None, philosophy_seed)
            publish("scheduler.global", "philosophy_seeded",
                    {"report_id": phil_id})
        except Exception as exc:
            log.warning("philosophy seed failed: %s", exc)
    elif day in (60, 90, 180, 365):
        try:
            from app.claude.philosophy import evolve as philosophy_evolve
            phil_id = await loop.run_in_executor(None, philosophy_evolve)
            publish("scheduler.global", "philosophy_evolved",
                    {"report_id": phil_id, "day_n": day})
        except Exception as exc:
            log.warning("philosophy evolve %d failed: %s", day, exc)
