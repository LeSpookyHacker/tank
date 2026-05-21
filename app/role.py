"""Single-row `app_state` helpers — role mode, internal TLD, tenure lens.

The `app_state` table holds at most one row (id=1). On first read we
upsert defaults, so callers can treat the state as always-present.

`current_lens()` returns the tenure-aware lens (map / prioritize /
execute / maintain) based on `tenure_started_at`. Chat system prompts
and reports adapt their tone accordingly.
"""

from __future__ import annotations

import json
import time
from typing import Literal

from app.db import LOCK, get_conn
from app.schemas import AppState, RoleMode, UserScope


Lens = Literal["map", "prioritize", "execute", "maintain"]


def _row_to_state(row) -> AppState:
    scope_raw = row["user_scope_json"] or "{}"
    try:
        scope = UserScope(**json.loads(scope_raw))
    except Exception:
        scope = UserScope()
    keys = set(row.keys())
    return AppState(
        role_mode=RoleMode(row["role_mode"]),
        internal_tld=row["internal_tld"],
        user_scope=scope,
        digest_time=row["digest_time"],
        reflection_day=row["reflection_day"],
        onboarded=bool(row["onboarded"]),
        tenure_started_at=row["tenure_started_at"] if "tenure_started_at" in keys else None,
        last_journal_at=row["last_journal_at"] if "last_journal_at" in keys else None,
        philosophy_doc_id=row["philosophy_doc_id"] if "philosophy_doc_id" in keys else None,
    )


def get_state() -> AppState:
    conn = get_conn()
    with LOCK:
        row = conn.execute(
            "SELECT * FROM app_state WHERE id = 1"
        ).fetchone()
        if row is None:
            now = time.time()
            conn.execute(
                "INSERT INTO app_state "
                "(id, role_mode, internal_tld, user_scope_json, digest_time, "
                " reflection_day, onboarded, updated_at) "
                "VALUES (1, 'both', NULL, '{}', '08:00', 'fri', 0, ?)",
                (now,),
            )
            row = conn.execute(
                "SELECT * FROM app_state WHERE id = 1"
            ).fetchone()
    return _row_to_state(row)


def update_state(
    *,
    role_mode: RoleMode | None = None,
    internal_tld: str | None = None,
    user_scope: UserScope | None = None,
    digest_time: str | None = None,
    reflection_day: str | None = None,
    onboarded: bool | None = None,
    tenure_started_at: float | None = None,
    last_journal_at: float | None = None,
) -> AppState:
    current = get_state()

    fields = []
    values: list = []
    if role_mode is not None:
        fields.append("role_mode = ?")
        values.append(role_mode.value)
    if internal_tld is not None:
        fields.append("internal_tld = ?")
        values.append(internal_tld or None)
    if user_scope is not None:
        fields.append("user_scope_json = ?")
        values.append(json.dumps(user_scope.model_dump()))
    if digest_time is not None:
        fields.append("digest_time = ?")
        values.append(digest_time)
    if reflection_day is not None:
        fields.append("reflection_day = ?")
        values.append(reflection_day)
    if onboarded is not None:
        fields.append("onboarded = ?")
        values.append(1 if onboarded else 0)
    if tenure_started_at is not None:
        fields.append("tenure_started_at = ?")
        values.append(tenure_started_at)
    if last_journal_at is not None:
        fields.append("last_journal_at = ?")
        values.append(last_journal_at)

    if not fields:
        return current

    fields.append("updated_at = ?")
    values.append(time.time())

    conn = get_conn()
    with LOCK:
        conn.execute(
            f"UPDATE app_state SET {', '.join(fields)} WHERE id = 1",
            values,
        )
    return get_state()


def tenure_day() -> int:
    """Days since the user completed onboarding. Returns 0 if not set."""
    s = get_state()
    if not s.tenure_started_at:
        return 0
    elapsed = time.time() - s.tenure_started_at
    return max(0, int(elapsed // 86400))


def current_lens() -> Lens:
    """Tenure-aware framing for the chat system prompt + dashboards.

    Map (1-14) → Prioritize (15-60) → Execute (61-180) → Maintain (180+).
    """
    day = tenure_day()
    if day <= 14:
        return "map"
    if day <= 60:
        return "prioritize"
    if day <= 180:
        return "execute"
    return "maintain"
