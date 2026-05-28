"""CRUD for ninety_day_plan."""
from __future__ import annotations

import json
import time
import uuid

from app.db import LOCK, get_conn


def create(items: list[dict]) -> str:
    pid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO ninety_day_plan (id, created_at, generated_at, items) "
            "VALUES (?, ?, ?, ?)",
            (pid, now, now, json.dumps(items)),
        )
    return pid


def get_latest() -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM ninety_day_plan ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["items"] = json.loads(d.get("items") or "[]")
    except Exception:
        d["items"] = []
    return d


def update_task(plan_id: str, task_index: int, done: bool) -> None:
    row = get_conn().execute(
        "SELECT items FROM ninety_day_plan WHERE id = ?", (plan_id,)
    ).fetchone()
    if not row:
        return
    try:
        items = json.loads(row["items"])
    except Exception:
        return
    if 0 <= task_index < len(items):
        items[task_index]["done"] = done
    conn = get_conn()
    with LOCK:
        conn.execute(
            "UPDATE ninety_day_plan SET items = ? WHERE id = ?",
            (json.dumps(items), plan_id),
        )


def current_week_tasks(plan_id: str, tenure_day: int) -> list[dict]:
    """Return tasks for the current week based on tenure day."""
    plan = get_latest()
    if not plan or plan["id"] != plan_id:
        plan = get_latest()
    if not plan:
        return []
    week_num = min(max((tenure_day // 7) + 1, 1), 13)
    return [t for t in plan["items"] if t.get("week") == week_num]
