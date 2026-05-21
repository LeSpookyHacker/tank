"""User-configurable redaction-rule toggles + custom patterns.

The built-in rules in `rules.py` (and `secrets.py`) each have an
`enabled_default`. Users may override that via the Settings UI; overrides
live in the `redaction_rules` table. They may also add fully-custom regex
rules that get compiled and applied alongside the built-ins.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable

from app.db import LOCK, get_conn
from app.redact.rules import ALL_RULES, Match, Rule


@dataclass
class CompiledRule:
    rule: Rule
    enabled: bool


def get_effective_rules() -> list[CompiledRule]:
    """Return the active rule list: built-ins overridden by user toggles
    plus any custom regex rules from `redaction_rules`."""
    conn = get_conn()
    with LOCK:
        rows = conn.execute(
            "SELECT id, category, enabled, pattern, placeholder_fmt, description "
            "FROM redaction_rules"
        ).fetchall()
    overrides = {r["category"]: bool(r["enabled"]) for r in rows
                 if r["pattern"] is None}
    customs = [r for r in rows if r["pattern"] is not None]

    out: list[CompiledRule] = []
    for r in ALL_RULES:
        enabled = overrides.get(r.category, r.enabled_default)
        if r.non_disableable:
            enabled = True
        out.append(CompiledRule(rule=r, enabled=enabled))

    for c in customs:
        if not c["enabled"]:
            continue
        try:
            compiled = re.compile(c["pattern"])
        except re.error:
            continue
        category = c["category"]
        placeholder_fmt = c["placeholder_fmt"] or f"[{category.upper()}_{{n:03d}}]"

        def make_finder(pat: re.Pattern, cat: str) -> Callable[[str], list[Match]]:
            def _find(text: str) -> list[Match]:
                return [
                    Match(m.start(), m.end(), m.group(0), cat)
                    for m in pat.finditer(text)
                ]
            return _find

        custom_rule = Rule(
            category=category,
            finder=make_finder(compiled, category),
            placeholder_fmt=placeholder_fmt,
            enabled_default=True,
            description=c["description"] or "",
        )
        out.append(CompiledRule(rule=custom_rule, enabled=True))
    return out


def set_category_enabled(category: str, enabled: bool) -> None:
    """Upsert an enabled/disabled override for a built-in category."""
    conn = get_conn()
    with LOCK:
        existing = conn.execute(
            "SELECT id FROM redaction_rules "
            "WHERE category = ? AND pattern IS NULL",
            (category,),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO redaction_rules "
                "(category, enabled, pattern, placeholder_fmt, description, "
                " created_at) VALUES (?, ?, NULL, NULL, NULL, ?)",
                (category, 1 if enabled else 0, time.time()),
            )
        else:
            conn.execute(
                "UPDATE redaction_rules SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, existing["id"]),
            )


def add_custom_rule(category: str, pattern: str,
                    placeholder_fmt: str | None = None,
                    description: str | None = None) -> int:
    """Add a user-supplied regex rule.

    Validates the regex compiles. Categories should be prefixed `custom:`
    by convention to avoid collisions with built-ins.
    """
    re.compile(pattern)   # raises re.error on bad regex
    if not category.startswith("custom:"):
        category = f"custom:{category}"
    conn = get_conn()
    with LOCK:
        cur = conn.execute(
            "INSERT INTO redaction_rules "
            "(category, enabled, pattern, placeholder_fmt, description, "
            " created_at) VALUES (?, 1, ?, ?, ?, ?)",
            (category, pattern, placeholder_fmt, description, time.time()),
        )
        return cur.lastrowid


def remove_custom_rule(rule_id: int) -> None:
    conn = get_conn()
    with LOCK:
        conn.execute(
            "DELETE FROM redaction_rules WHERE id = ? AND pattern IS NOT NULL",
            (rule_id,),
        )
