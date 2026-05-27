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
_ANNIVERSARIES = {30, 60, 90, 180, 365}


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
    return (dt or _now()).strftime("%Y-%m-%d")


def _week_label(dt: datetime | None = None) -> str:
    d = dt or _now()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def start() -> None:
    """Start the scheduler task. Called once from lifespan."""
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    _TASK = asyncio.create_task(_run(), name="tank-scheduler")
    log.info("scheduler started")


def stop() -> None:
    global _TASK
    if _TASK is not None:
        _TASK.cancel()
        _TASK = None
        log.info("scheduler stopped")


def is_running() -> bool:
    return _TASK is not None and not _TASK.done()


async def _run() -> None:
    try:
        while True:
            try:
                await _tick()
            except Exception as exc:
                log.exception("scheduler tick failed: %s", exc)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        log.info("scheduler cancelled")
        raise


async def _tick() -> None:
    now = _now()
    today_label = _today_label(now)
    week_label = _week_label(now)
    hhmm = now.strftime("%H:%M")
    weekday_short = now.strftime("%a").lower()[:3]
    state = get_state()

    if hhmm >= state.digest_time and \
            not scheduler_state_store.has_fired("digest", today_label):
        await _fire_digest(today_label)

    if weekday_short == state.reflection_day.lower()[:3] \
            and hhmm >= "16:00" \
            and not scheduler_state_store.has_fired("reflection", today_label):
        await _fire_reflection(today_label)

    if now.weekday() < 5 and hhmm >= "18:00" \
            and not scheduler_state_store.has_fired("journal_prompt", today_label):
        await _fire_journal_prompt(today_label)

    if hhmm >= "22:00" \
            and not scheduler_state_store.has_fired("auto_briefs", today_label):
        await _fire_auto_briefs(today_label)

    if weekday_short == "sun" and hhmm >= "09:00" \
            and not scheduler_state_store.has_fired(
                "attack_surface_snapshot", week_label):
        await _fire_attack_surface_snapshot(week_label)

    if weekday_short == "sun" and hhmm >= "09:30" \
            and not scheduler_state_store.has_fired(
                "security_program_snapshot", week_label):
        await _fire_security_program_snapshot(week_label)

    if weekday_short == "sun" and hhmm >= "03:00" \
            and not scheduler_state_store.has_fired(
                "weekly_backup", week_label):
        await _fire_weekly_backup(week_label)


# ---------------- job bodies ----------------

async def _fire_digest(today_label: str) -> None:
    scheduler_state_store.mark_fired("digest", today_label)
    log.info("digest firing for %s", today_label)
    publish("scheduler.global", "digest_fired", {"date": today_label})

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
    scheduler_state_store.mark_fired("reflection", today_label)
    log.info("weekly reflection firing for %s", today_label)
    publish("scheduler.global", "reflection_due", {"date": today_label})


async def _fire_journal_prompt(today_label: str) -> None:
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
    scheduler_state_store.mark_fired("auto_briefs", today_label)
    try:
        from app.storage import meetings_store
    except Exception:
        return
    from app.claude import meeting_prep as mp_mod

    start = time.time() + 4 * 3600
    end = time.time() + 36 * 3600
    upcoming = meetings_store.list_between(start, end) \
        if hasattr(meetings_store, "list_between") else []
    loop = asyncio.get_event_loop()
    generated = 0
    for m in upcoming:
        if generated >= 5:
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
    """Online SQLite backup. Keeps the last 8 weekly snapshots."""
    scheduler_state_store.mark_fired("weekly_backup", week_label)
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _take_backup)
        publish("scheduler.global", "weekly_backup", {"week": week_label})
    except Exception as exc:
        log.warning("weekly backup failed: %s", exc)


def _take_backup() -> None:
    """Run inside the executor — uses sqlite3 .backup which is online-safe."""
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

    # Retention: drop anything beyond the last 8.
    for stale in backup_log_store.stale(keep_n=8):
        p = Path(stale["path"])
        if p.exists():
            try:
                p.unlink()
            except OSError as exc:
                log.warning("could not unlink %s: %s", p, exc)
        backup_log_store.delete_record(stale["id"])


async def _run_due_subscriptions() -> None:
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
