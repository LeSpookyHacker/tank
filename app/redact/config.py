"""User-configurable redaction-rule toggles + custom patterns.

The built-in rules in `rules.py` (and `secrets.py`) each have an
`enabled_default`. Users may override that via the Settings UI; overrides
live in the `redaction_rules` table. They may also add fully-custom regex
rules that get compiled and applied alongside the built-ins.
"""

from __future__ import annotations

import re
import signal
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


def _reject_redos(pattern: str) -> None:
    """Raise re.error if the pattern causes catastrophic backtracking.

    Runs the compiled pattern against a 40-character adversarial string
    (`aaaa...!`) under a 1-second SIGALRM deadline. A ReDoS-prone pattern
    hits exponential backtracking at that length (2^40 paths) and always
    triggers the alarm; a safe pattern finishes in well under 1 ms.

    SIGALRM is Unix-only and must be called from the main thread.  Both
    conditions hold here: Tank runs on Linux and async FastAPI routes execute
    on the event-loop (main) thread.  Tests run on the main pytest thread.
    """
    compiled = re.compile(pattern)

    def _alarm(signum, frame):
        raise re.error(
            "pattern timed out against adversarial input — "
            "likely susceptible to catastrophic backtracking (ReDoS)"
        )

    for size in (40, 100, 200):
        adversarial = "a" * size + "!"
        old_handler = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(1)
        try:
            compiled.search(adversarial)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


# Only allow placeholder formats of the form [PREFIX_{n}] or [PREFIX_{n:03d}].
# This prevents format-string injection via oversized width specs ({n:9999999d})
# or attribute traversal ({n.__class__}) in store.upsert_match.
_VALID_PLACEHOLDER_FMT = re.compile(
    r"^\[[A-Z][A-Z0-9_]{0,30}_\{n(?::\d{1,3}d)?\}\]$"
)


def add_custom_rule(category: str, pattern: str,
                    placeholder_fmt: str | None = None,
                    description: str | None = None) -> int:
    """Add a user-supplied regex rule.

    Validates the regex compiles, checks for ReDoS-prone constructs, and
    restricts placeholder_fmt to the safe [PREFIX_{n:03d}] form.
    Categories should be prefixed `custom:` by convention to avoid
    collisions with built-ins.
    """
    re.compile(pattern)   # raises re.error on bad regex syntax
    _reject_redos(pattern)
    if placeholder_fmt is not None and not _VALID_PLACEHOLDER_FMT.match(placeholder_fmt):
        raise ValueError(
            "placeholder_fmt must match [PREFIX_{n}] or [PREFIX_{n:03d}], "
            "e.g. [CUSTOM_EMAIL_{n:03d}]"
        )
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
