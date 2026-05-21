"""Core redaction engine.

`apply_redactions(text)` walks every enabled rule, collects matches,
resolves overlaps deterministically (earlier rule wins, then longer
match), persists each match to the redaction_map (allocating or reusing
a placeholder), and returns the redacted text plus the set of matches.

`rehydrate(text, mapping)` replaces placeholders with originals. Replace-
ment is longest-placeholder-first to prevent `[HOST_1]` from clobbering
`[HOST_10]`. Caller supplies the mapping so we can scope rehydration to
just the placeholders we sent (defense in depth).

`scrub_for_send(text)` is a convenience for the chat / report code paths:
runs apply_redactions and returns just the redacted string.
"""

from __future__ import annotations

from app.redact.config import get_effective_rules
from app.redact.rules import Match
from app.redact.store import load_rehydration_map, upsert_match
from app.schemas import RedactionMatch, RedactionResult


# Importing secrets.py for its side effect: it appends SECRET_RULE +
# PERSON_RULE to the ALL_RULES registry. Tests of the engine therefore
# get the same rule set as production.
from app.redact import secrets as _secrets  # noqa: F401


def _resolve_overlaps(matches: list[Match]) -> list[Match]:
    """Keep matches that don't overlap previously-kept ones.

    Rule order in ALL_RULES is significant — more-specific rules come
    first. Within the same call, we sort by (start, -length) so the
    earliest, longest match wins.
    """
    matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    kept: list[Match] = []
    last_end = -1
    for m in matches:
        if m.start < last_end:
            continue
        kept.append(m)
        last_end = m.end
    return kept


def apply_redactions(text: str) -> RedactionResult:
    """Redact `text` in place. Returns redacted output + match metadata.

    Side effects:
    - Each unique (category, original) pair is upserted into redaction_map.
    - For category 'secret_token', original_text is stored as a SHA256 hash
      (see store.upsert_match).
    """
    rules = get_effective_rules()

    all_matches: list[tuple[Match, str]] = []  # (match, placeholder_fmt)
    for cr in rules:
        if not cr.enabled:
            continue
        for m in cr.rule.finder(text):
            all_matches.append((m, cr.rule.placeholder_fmt))

    # Resolve overlaps based on absolute position; rule precedence is
    # implicit in the order we appended.
    by_pos: dict[tuple[int, int], tuple[Match, str]] = {}
    for m, fmt in all_matches:
        key = (m.start, m.end)
        if key not in by_pos:
            by_pos[key] = (m, fmt)

    flat = list(by_pos.values())
    flat.sort(key=lambda x: (x[0].start, -(x[0].end - x[0].start)))

    kept: list[tuple[Match, str]] = []
    last_end = -1
    for m, fmt in flat:
        if m.start < last_end:
            continue
        kept.append((m, fmt))
        last_end = m.end

    # Allocate placeholders (stable across calls) and build the redacted
    # output by walking left-to-right.
    pieces: list[str] = []
    cursor = 0
    match_records: list[RedactionMatch] = []
    counts: dict[str, int] = {}

    for m, fmt in kept:
        placeholder = upsert_match(m.category, m.original, fmt)
        pieces.append(text[cursor:m.start])
        pieces.append(placeholder)
        cursor = m.end
        counts[placeholder] = counts.get(placeholder, 0) + 1
        match_records.append(RedactionMatch(
            category=m.category,
            placeholder=placeholder,
            original=m.original,
            occurrences=1,
        ))
    pieces.append(text[cursor:])

    # Collapse same-placeholder matches in the result for readability.
    collapsed: dict[str, RedactionMatch] = {}
    for rec in match_records:
        if rec.placeholder in collapsed:
            collapsed[rec.placeholder].occurrences += 1
        else:
            collapsed[rec.placeholder] = rec

    return RedactionResult(
        redacted_text="".join(pieces),
        matches=list(collapsed.values()),
    )


def rehydrate(text: str, mapping: dict[str, str] | None = None) -> str:
    """Restore original text by replacing placeholders.

    If `mapping` is None we pull the full redaction map. Pass an explicit
    mapping when you only want to rehydrate placeholders you actually
    sent — keeps the substitution set narrow.
    """
    if mapping is None:
        mapping = load_rehydration_map()
    if not mapping:
        return text
    # Longest first so `[HOST_10]` is replaced before `[HOST_1]`.
    for placeholder in sorted(mapping.keys(), key=len, reverse=True):
        text = text.replace(placeholder, mapping[placeholder])
    return text


def scrub_for_send(text: str) -> str:
    """Convenience: apply_redactions and return just the redacted string."""
    return apply_redactions(text).redacted_text
