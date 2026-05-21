"""Opt-in connector configuration endpoints."""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import LOCK, get_conn
from app.ingest.watchers import dispatch

router = APIRouter(prefix="/api/integrations")


class CreateWatcher(BaseModel):
    kind: str        # folder|ics_url|cve_feed|github_repo
    target: str
    category: str | None = None
    config: dict | None = None


@router.get("/watchers")
async def list_watchers() -> dict:
    rows = get_conn().execute(
        "SELECT * FROM watchers ORDER BY created_at DESC"
    ).fetchall()
    return {"watchers": [dict(r) for r in rows]}


@router.post("/watchers")
async def create_watcher(body: CreateWatcher) -> dict:
    if dispatch(body.kind) is None:
        raise HTTPException(400, f"unknown watcher kind: {body.kind}")
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
