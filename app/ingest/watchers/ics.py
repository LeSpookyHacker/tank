"""ICS calendar watcher: fetch a public/CalDAV .ics URL, populate the
`meetings` table.

Lean implementation — uses stdlib only (`urllib`) to fetch the .ics
file and a basic event parser. Doesn't handle recurrence rules
(RRULE), which is fine for the demo case where users just want their
upcoming weekly schedule.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import Iterable

from app.db import LOCK, get_conn

log = logging.getLogger("tank.watchers.ics")

_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal"}


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme: {parsed.scheme}")
    host = parsed.hostname or ""
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"blocked metadata host: {host}")
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError(f"blocked private address: {host}")
    except ValueError as exc:
        if "blocked" in str(exc):
            raise


_EVENT_BLOCK_RE = re.compile(
    r"BEGIN:VEVENT\s*\r?\n(.*?)\r?\nEND:VEVENT",
    re.DOTALL,
)


def _parse_ics_datetime(s: str) -> float | None:
    """Parse 20260520T140000Z (or with tz suffix) → unix timestamp."""
    s = s.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return None


def _parse_events(ics_text: str) -> Iterable[dict]:
    for match in _EVENT_BLOCK_RE.finditer(ics_text):
        block = match.group(1)
        ev: dict = {"attendees": []}
        for line in block.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            # Strip params (e.g. DTSTART;TZID=America/Los_Angeles:...)
            key_part, value = line.split(":", 1)
            key = key_part.split(";")[0].upper()
            if key == "SUMMARY":
                ev["title"] = value
            elif key == "DTSTART":
                ts = _parse_ics_datetime(value)
                if ts:
                    ev["starts_at"] = ts
            elif key == "DTEND":
                ts = _parse_ics_datetime(value)
                if ts:
                    ev["ends_at"] = ts
            elif key == "UID":
                ev["external_id"] = value
            elif key == "ATTENDEE":
                ev["attendees"].append(value)
        if ev.get("title") and ev.get("starts_at"):
            yield ev


class ICSWatcher:
    def scan(self, watcher: dict) -> dict:
        url = watcher["target"]
        try:
            _validate_url(url)
            with urllib.request.urlopen(url, timeout=15) as resp:
                ics_text = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return {"error": str(exc)}

        events = list(_parse_events(ics_text))
        added = 0
        conn = get_conn()
        with LOCK:
            for ev in events:
                existing = conn.execute(
                    "SELECT id FROM meetings WHERE external_id = ?",
                    (ev.get("external_id"),),
                ).fetchone() if ev.get("external_id") else None
                if existing:
                    continue
                conn.execute(
                    "INSERT INTO meetings "
                    "(id, external_id, title, starts_at, ends_at, "
                    " attendees_json, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'ics', ?)",
                    (uuid.uuid4().hex, ev.get("external_id"),
                     ev["title"], ev["starts_at"], ev.get("ends_at"),
                     str(ev.get("attendees") or []),
                     time.time()),
                )
                added += 1
        return {"events_found": len(events),
                "events_added": added,
                "scanned_at": time.time()}
