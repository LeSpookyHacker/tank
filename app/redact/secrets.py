"""Secret token detection.

Two layers:
1. `detect-secrets` plugin scan — catches AWS keys, GitHub tokens, JWTs,
   PEM blocks, Slack tokens, GCP service-account keys, generic high-
   entropy strings tagged by Yelp's curated plugin set.
2. Entropy fallback — any base64-ish or hex token >=20 chars with
   Shannon entropy >=4.5 that the plugins missed.

The secret_token rule is ALWAYS ON; the UI hides the toggle. Originals
are NEVER persisted in cleartext (see `store.upsert_match` for the
hashing of `original_text` when category == 'secret_token').

Person-name redaction is here too, since it also requires a heavy
external dep (spaCy) and is conceptually similar (off by default).
"""

from __future__ import annotations

import math
import re

from app.config import ENABLE_PERSON_REDACTION
from app.redact.rules import ALL_RULES, Match, Rule

# Lazy globals — instantiated on first call so importing this module is cheap.
_SECRETS_COLLECTION = None
_NLP = None


# ---------------- detect-secrets plugin scan ----------------

# Curated detect-secrets plugin list.
#
# detect-secrets ships ~20 plugins by default. The `KeywordDetector` and
# `BasicAuthDetector` are notoriously false-positive-heavy (they trip on
# words like "password", "secret", and any 3-letter token near them).
# We restrict to plugins that match well-known token *shapes* and rely on
# our own Shannon-entropy fallback for anything else.
_DS_PLUGINS = [
    {"name": "AWSKeyDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "GitLabTokenDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "SlackDetector"},
    {"name": "StripeDetector"},
    {"name": "TwilioKeyDetector"},
    {"name": "MailchimpDetector"},
    {"name": "DiscordBotTokenDetector"},
    {"name": "SendGridDetector"},
    {"name": "SquareOAuthDetector"},
]

# Patterns for common secret formats not covered by detect-secrets plugins.
# AWSKeyDetector covers long-term keys (AKIA); session/assumed-role keys
# start with ASIA and are not matched by that plugin.
_EXTRA_SECRET_RES: list[re.Pattern] = [
    re.compile(r"\bASIA[A-Z0-9]{16}\b"),                    # AWS STS session key
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),         # GitHub fine-grained PAT
    re.compile(r"DefaultEndpointsProtocol=https?;[^\s\"']{20,}"),  # Azure conn string
    re.compile(r"\bAIza[A-Za-z0-9\-_]{35}\b"),              # GCP API key
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),                 # GitHub classic PAT (belt+suspenders)
]


def _find_extra_secrets(text: str) -> list[Match]:
    out: list[Match] = []
    for pat in _EXTRA_SECRET_RES:
        for m in pat.finditer(text):
            out.append(Match(m.start(), m.end(), m.group(0), "secret_token"))
    return out


def _get_secrets_collection():
    global _SECRETS_COLLECTION
    if _SECRETS_COLLECTION is not None:
        return _SECRETS_COLLECTION
    try:
        from detect_secrets.core.scan import scan_line
        from detect_secrets.settings import transient_settings
    except ImportError:
        _SECRETS_COLLECTION = ("missing", None)
        return _SECRETS_COLLECTION
    _SECRETS_COLLECTION = ("ok", (scan_line, transient_settings))
    return _SECRETS_COLLECTION


def _find_via_detect_secrets(text: str) -> list[Match]:
    status, payload = _get_secrets_collection()
    if status != "ok":
        return []
    scan_line, transient_settings = payload

    out: list[Match] = []
    offset = 0
    with transient_settings({"plugins_used": _DS_PLUGINS}):
        for line in text.splitlines(keepends=True):
            for potential in scan_line(line):
                tok = potential.secret_value
                if not tok:
                    continue
                idx = line.find(tok)
                if idx == -1:
                    continue
                start = offset + idx
                end = start + len(tok)
                out.append(Match(start, end, tok, "secret_token"))
            offset += len(line)
    return out


# ---------------- entropy fallback ----------------

# Note: underscore is intentionally excluded from the entropy-fallback
# character class. Tokens with `_` are almost always snake_case
# identifiers (env var names, schema fields) — letting them through here
# would trip on harmless code-like strings. Real secrets (AWS keys,
# GitHub PATs, Slack tokens, JWTs) never contain underscores.
_BASE64ISH_RE = re.compile(r"[A-Za-z0-9+/\-=]{20,}")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _find_high_entropy(text: str, *, already_redacted: set[tuple[int, int]]
                       ) -> list[Match]:
    """High-entropy tokens not already caught by detect-secrets."""
    out: list[Match] = []
    for m in _BASE64ISH_RE.finditer(text):
        # Skip if this span is already covered by a detect-secrets hit
        # (or any earlier rule).
        span = (m.start(), m.end())
        if any(s <= m.start() and m.end() <= e for s, e in already_redacted):
            continue
        tok = m.group(0)
        if _shannon_entropy(tok) < 4.5:
            continue
        # Skip obvious non-secrets — long identifier-like words with vowels.
        if _looks_like_natural_text(tok):
            continue
        out.append(Match(m.start(), m.end(), tok, "secret_token"))
    return out


_VOWELS = set("aeiouAEIOU")


def _looks_like_natural_text(s: str) -> bool:
    if len(s) < 24:
        # Short tokens — let entropy decide.
        return False
    vowels = sum(1 for c in s if c in _VOWELS)
    return vowels / len(s) > 0.30


# ---------------- combined finder ----------------

def find_secrets(text: str) -> list[Match]:
    """Detect-secrets plugins + extra patterns + entropy fallback, deduplicated by span."""
    primary = _find_via_detect_secrets(text) + _find_extra_secrets(text)
    primary_spans = {(m.start, m.end) for m in primary}
    secondary = _find_high_entropy(text, already_redacted=primary_spans)
    return primary + secondary


# ---------------- person names (optional) ----------------

def _get_nlp():
    global _NLP
    if _NLP is not None:
        return _NLP
    try:
        import spacy
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = "missing"
    return _NLP


def find_person_names(text: str) -> list[Match]:
    if not ENABLE_PERSON_REDACTION:
        return []
    nlp = _get_nlp()
    if nlp == "missing":
        return []
    out: list[Match] = []
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            out.append(Match(ent.start_char, ent.end_char, ent.text, "person_name"))
    return out


# ---------------- register ----------------

SECRET_RULE = Rule(
    category="secret_token",
    finder=find_secrets,
    placeholder_fmt="[SECRET_{n:03d}]",
    non_disableable=True,
    description="API keys, tokens, PEM blocks, JWTs, and high-entropy strings.",
)

PERSON_RULE = Rule(
    category="person_name",
    finder=find_person_names,
    placeholder_fmt="[PERSON_{n:03d}]",
    enabled_default=False,
    description="Person names via spaCy NER. Off by default — flipping it on "
                "degrades conversational utility.",
)


def install_into_registry() -> None:
    """Append secret + person rules to the global registry.

    Called once at module import time below. Idempotent.
    """
    existing = {r.category for r in ALL_RULES}
    if SECRET_RULE.category not in existing:
        ALL_RULES.append(SECRET_RULE)
    if PERSON_RULE.category not in existing:
        ALL_RULES.append(PERSON_RULE)


install_into_registry()
