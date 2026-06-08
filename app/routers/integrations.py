"""Opt-in connector configuration endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import LOCK, get_conn
from app.ingest.path_guard import is_blocked_path
from app.ingest.watchers import dispatch

log = logging.getLogger("tank.routers.integrations")

router = APIRouter(prefix="/api/integrations")

_ALLOWED_WATCHER_KINDS = {"folder", "ics_url", "cve_feed", "github_repo"}


class CreateWatcher(BaseModel):
    kind: str        # folder|ics_url|cve_feed|github_repo
    target: str
    category: str | None = None
    config: dict | None = None


_GITHUB_REPO_RE = __import__("re").compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")


def _validate_watcher_target(kind: str, target: str) -> None:
    """Reject obviously dangerous targets at creation time."""
    if kind == "folder":
        try:
            p = Path(target).resolve()
        except Exception:
            raise HTTPException(400, "invalid folder path")
        blocked = is_blocked_path(p)
        if blocked:
            log.warning("blocked watcher folder target: %s (matched: %s)", p, blocked)
            raise HTTPException(400, "folder target not allowed")
    elif kind == "github_repo":
        if not _GITHUB_REPO_RE.match(target):
            raise HTTPException(
                400,
                "github_repo target must be 'owner/repo' "
                "(alphanumeric, hyphens, underscores, and dots only)",
            )
    elif kind == "ics_url":
        try:
            parsed = urlparse(target)
        except Exception:
            raise HTTPException(400, "invalid ICS URL")
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(400, "ics_url target must use http:// or https://")
        if not parsed.hostname:
            raise HTTPException(400, "ics_url target must include a hostname")
    elif kind == "cve_feed":
        try:
            parsed = urlparse(target)
        except Exception:
            raise HTTPException(400, "invalid CVE feed URL")
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(400, "cve_feed target must use http:// or https://")
        if not parsed.hostname:
            raise HTTPException(400, "cve_feed target must include a hostname")


@router.get("/watchers")
async def list_watchers() -> dict:
    rows = get_conn().execute(
        "SELECT * FROM watchers ORDER BY created_at DESC"
    ).fetchall()
    return {"watchers": [dict(r) for r in rows]}


@router.post("/watchers")
async def create_watcher(body: CreateWatcher) -> dict:
    if body.kind not in _ALLOWED_WATCHER_KINDS or dispatch(body.kind) is None:
        raise HTTPException(400, f"unknown watcher kind: {body.kind!r}")
    _validate_watcher_target(body.kind, body.target)
    wid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO watchers "
            "(id, kind, target, category, config_json, last_scan_at, "
            " enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, 1, ?)",
            (wid, body.kind, body.target, body.category,
             json.dumps(body.config or {}), time.time()),
        )
    return {"id": wid}


@router.post("/watchers/{watcher_id}/scan")
async def scan_now(watcher_id: str) -> dict:
    row = get_conn().execute(
        "SELECT * FROM watchers WHERE id = ?", (watcher_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "no such watcher")
    cls = dispatch(row["kind"])
    if cls is None:
        raise HTTPException(400, f"unknown kind: {row['kind']}")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, cls().scan, dict(row))
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE watchers SET last_scan_at = ? WHERE id = ?",
            (time.time(), watcher_id),
        )
    return {"result": result}


@router.delete("/watchers/{watcher_id}")
async def delete_watcher(watcher_id: str) -> dict:
    conn = get_conn()
    with LOCK:
        conn.execute("DELETE FROM watchers WHERE id = ?", (watcher_id,))
    return {"ok": True}


@router.post("/watchers/{watcher_id}/toggle")
async def toggle_watcher(watcher_id: str, enabled: bool) -> dict:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE watchers SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, watcher_id),
        )
    return {"ok": True}
