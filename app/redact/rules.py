"""Built-in redaction rule definitions.

Each rule has:
- category: stable identifier used as the placeholder prefix and the
  redaction_map.category column. Once shipped, NEVER rename — that would
  orphan placeholders in already-redacted chunks.
- finder: a callable (text, ctx) -> list[Match] where Match captures the
  span and the original text. Letting rules pick spans (rather than just
  returning regexes) lets some rules check context (e.g. AWS account ID
  near AWS keywords).
- placeholder_fmt: a format string with one positional argument — the
  sequence number (or shared SHA-derived id) for this match.
- enabled_default: whether the rule is on by default. Some rules
  (public hostnames, person names) degrade the conversational utility
  so we leave them off until the user opts in.
- non_disableable: the secret_token rule can't be turned off.

Detection rules live here. The engine in `engine.py` walks them in order,
records matches against the redaction_map, and substitutes placeholders.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Callable

from app.config import INTERNAL_TLD


@dataclass(frozen=True)
class Match:
    """A single redaction-eligible span."""
    start: int
    end: int
    original: str
    category: str


@dataclass(frozen=True)
class Rule:
    category: str
    finder: Callable[[str], list[Match]]
    placeholder_fmt: str
    enabled_default: bool = True
    non_disableable: bool = False
    description: str = ""


# ---------------- helpers ----------------

def _spans(pattern: re.Pattern, text: str, category: str,
           group: int = 0) -> list[Match]:
    return [
        Match(m.start(group), m.end(group), m.group(group), category)
        for m in pattern.finditer(text)
    ]


# ---------------- patterns ----------------

# Email: standard local-part + domain, conservative bounds.
EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Internal TLDs that are always treated as internal.
DEFAULT_INTERNAL_SUFFIXES = ("internal", "corp", "local", "lan", "intra")

# Hostname: dotted, alpha-numeric labels, optional underscore in labels,
# at least one dot. We post-filter to internal vs public.
HOSTNAME_RE = re.compile(
    r"\b(?=[A-Za-z0-9])"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}\b"
)

# IPv4 in dotted form. We post-classify private vs public.
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)

# IPv6 — all valid compressed/full forms. We use ipaddress.ip_address() to
# validate and classify rather than trying to encode the logic in the regex.
# The pattern is intentionally broad; the finder post-validates via stdlib.
# Requires at least two colon-separated hex groups to avoid matching
# short hex strings that happen to contain a colon (e.g. CSS #rgb).
IPV6_RE = re.compile(
    r"(?<![:\w])"                       # not preceded by colon or word char
    r"(?:"
    r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}"                   # full
    r"|(?:[0-9a-fA-F]{1,4}:){1,7}:"                                 # trailing ::
    r"|(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}"
    r"|(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}"
    r"|(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}"
    r"|(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}"
    r"|(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}"
    r"|[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}"
    r"|:(?::[0-9a-fA-F]{1,4}){1,7}"
    r"|::"                                                           # all-zeros
    r")"
    r"(?![:\w])"                         # not followed by colon or word char
)

# AWS-ish patterns.
AWS_ACCT_RE = re.compile(r"\b\d{12}\b")
AWS_ARN_RE = re.compile(
    # Account ID and region may both be empty for service-level ARNs
    # like `arn:aws:s3:::my-bucket`. We tolerate that.
    r"arn:aws(?:-[a-z\-]+)?:[a-z0-9\-]+:[a-z0-9\-]*:[a-z0-9\-]*:[^\s\"']+"
)
AWS_CONTEXT_WORDS = (
    "aws", "amazon", "arn:", "account", "accountid", "account_id",
    "iam", "s3", "ec2", "lambda", "sts", "assume",
)

# GCP project IDs are 6–30 chars, lower-alpha-numeric and hyphens, must
# start with a lowercase letter. We require a GCP-context word nearby.
GCP_PROJECT_RE = re.compile(r"\b[a-z][a-z0-9\-]{4,28}[a-z0-9]\b")
GCP_CONTEXT_WORDS = ("gcp", "google cloud", "project_id", "project-id", "projectid")

# Azure subscription IDs are UUIDs.
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
AZURE_CONTEXT_WORDS = ("azure", "subscription", "tenant", "aad", "entra")


# ---------------- finders ----------------

def find_emails(text: str) -> list[Match]:
    return _spans(EMAIL_RE, text, "email")


def _is_internal_hostname(host: str) -> bool:
    host = host.lower()
    if INTERNAL_TLD and (host == INTERNAL_TLD or host.endswith("." + INTERNAL_TLD)):
        return True
    parts = host.split(".")
    return parts[-1] in DEFAULT_INTERNAL_SUFFIXES


def find_internal_hostnames(text: str) -> list[Match]:
    out: list[Match] = []
    for m in HOSTNAME_RE.finditer(text):
        host = m.group(0)
        # Skip email domains — emails are handled separately and may overlap.
        # Heuristic: if the char before the hostname is '@', it's an email part.
        if m.start() > 0 and text[m.start() - 1] == "@":
            continue
        if _is_internal_hostname(host):
            out.append(Match(m.start(), m.end(), host, "internal_hostname"))
    return out


def find_public_hostnames(text: str) -> list[Match]:
    out: list[Match] = []
    for m in HOSTNAME_RE.finditer(text):
        host = m.group(0)
        if m.start() > 0 and text[m.start() - 1] == "@":
            continue
        if not _is_internal_hostname(host):
            out.append(Match(m.start(), m.end(), host, "public_hostname"))
    return out


def _is_private_ipv4(ip: str) -> bool:
    try:
        a, b, _c, _d = (int(p) for p in ip.split("."))
    except ValueError:
        return False
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 127:
        return True
    if a == 169 and b == 254:
        return True
    # CGNAT 100.64.0.0/10
    if a == 100 and 64 <= b <= 127:
        return True
    return False


def find_private_ipv4(text: str) -> list[Match]:
    out: list[Match] = []
    for m in IPV4_RE.finditer(text):
        ip = m.group(0)
        if _is_private_ipv4(ip):
            out.append(Match(m.start(), m.end(), ip, "ipv4_private"))
    return out


def find_public_ipv4(text: str) -> list[Match]:
    out: list[Match] = []
    for m in IPV4_RE.finditer(text):
        ip = m.group(0)
        if not _is_private_ipv4(ip):
            out.append(Match(m.start(), m.end(), ip, "ipv4_public"))
    return out


def _is_private_ipv6(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return (addr.is_private or addr.is_loopback
                or addr.is_link_local or addr.is_unspecified)
    except ValueError:
        return False


def find_private_ipv6(text: str) -> list[Match]:
    out: list[Match] = []
    for m in IPV6_RE.finditer(text):
        ip = m.group(0)
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        if _is_private_ipv6(ip):
            out.append(Match(m.start(), m.end(), ip, "ipv6_private"))
    return out


def find_public_ipv6(text: str) -> list[Match]:
    out: list[Match] = []
    for m in IPV6_RE.finditer(text):
        ip = m.group(0)
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not _is_private_ipv6(ip):
            out.append(Match(m.start(), m.end(), ip, "ipv6_public"))
    return out


def _has_context(text: str, span_start: int, span_end: int,
                 words: tuple[str, ...], window: int = 64) -> bool:
    """True if any context word appears within `window` chars of the span."""
    lo = max(0, span_start - window)
    hi = min(len(text), span_end + window)
    haystack = text[lo:hi].lower()
    return any(w in haystack for w in words)


def find_aws_accounts(text: str) -> list[Match]:
    out: list[Match] = []
    for m in AWS_ACCT_RE.finditer(text):
        if _has_context(text, m.start(), m.end(), AWS_CONTEXT_WORDS):
            out.append(Match(m.start(), m.end(), m.group(0), "aws_account_id"))
    return out


def find_aws_arns(text: str) -> list[Match]:
    return _spans(AWS_ARN_RE, text, "aws_arn")


def find_gcp_projects(text: str) -> list[Match]:
    out: list[Match] = []
    # GCP project IDs collide with normal English words, so context is mandatory.
    lower = text.lower()
    if not any(w in lower for w in GCP_CONTEXT_WORDS):
        return out
    for m in GCP_PROJECT_RE.finditer(text):
        if _has_context(text, m.start(), m.end(), GCP_CONTEXT_WORDS, window=80):
            tok = m.group(0)
            # Skip common English words that match the pattern.
            if tok in _COMMON_WORDS:
                continue
            out.append(Match(m.start(), m.end(), tok, "gcp_project"))
    return out


def find_azure_subscriptions(text: str) -> list[Match]:
    out: list[Match] = []
    for m in UUID_RE.finditer(text):
        if _has_context(text, m.start(), m.end(), AZURE_CONTEXT_WORDS):
            out.append(Match(m.start(), m.end(), m.group(0), "azure_subscription"))
    return out


# Stop-list for GCP project ID detection: words that match the pattern
# ([a-z][a-z0-9\-]{4,28}[a-z0-9]) but are common English / architecture terms.
_COMMON_WORDS = frozenset({
    "service", "services", "project", "projects", "platform", "production",
    "staging", "environment", "configuration", "deployment", "deployments",
    "infrastructure", "monitoring", "permissions", "credentials",
    # common compound architecture terms that would false-positive heavily
    "authentication", "authorization", "notification", "integration",
    "application", "management", "processing", "container", "kubernetes",
    "microservice", "database", "repository", "development", "organization",
    "architecture", "foundation", "automation", "orchestration", "validation",
    "ingestion", "transformation", "aggregation", "collection", "discovery",
    "annotation", "recommendation", "classification", "registration",
    "subscription", "distribution", "replication", "synchronization",
})


# ---------------- registry ----------------

# Order matters: more-specific rules first. Internal hostnames must come
# before public hostnames or the public rule would swallow internal hits;
# ARNs must come before AWS account IDs because an ARN contains a 12-digit
# account number we don't want to redact twice.
ALL_RULES: list[Rule] = [
    Rule(
        category="email",
        finder=find_emails,
        placeholder_fmt="[EMAIL_{n:03d}]",
        description="Email addresses.",
    ),
    Rule(
        category="aws_arn",
        finder=find_aws_arns,
        placeholder_fmt="[AWS_ARN_{n:03d}]",
        description="Full AWS ARNs (account + resource portion).",
    ),
    Rule(
        category="aws_account_id",
        finder=find_aws_accounts,
        placeholder_fmt="[AWS_ACCT_{n:03d}]",
        description="12-digit AWS account IDs near AWS context keywords.",
    ),
    Rule(
        category="azure_subscription",
        finder=find_azure_subscriptions,
        placeholder_fmt="[AZURE_SUB_{n:03d}]",
        description="Azure subscription / tenant UUIDs near Azure context.",
    ),
    Rule(
        category="gcp_project",
        finder=find_gcp_projects,
        placeholder_fmt="[GCP_PROJECT_{n:03d}]",
        description="GCP project IDs near GCP context keywords.",
    ),
    Rule(
        category="internal_hostname",
        finder=find_internal_hostnames,
        placeholder_fmt="[INTERNAL_HOST_{n:03d}]",
        description="Hostnames under internal TLDs (.internal, .corp, .local, "
                    "your configured internal TLD, etc.).",
    ),
    Rule(
        category="public_hostname",
        finder=find_public_hostnames,
        placeholder_fmt="[HOST_{n:03d}]",
        enabled_default=False,
        description="All other dotted hostnames. Off by default — public "
                    "domains often carry useful context (vendor SaaS).",
    ),
    Rule(
        category="ipv4_private",
        finder=find_private_ipv4,
        placeholder_fmt="[PRIVATE_IP_{n:03d}]",
        description="RFC1918 / loopback / link-local / CGNAT IPv4 addresses.",
    ),
    Rule(
        category="ipv4_public",
        finder=find_public_ipv4,
        placeholder_fmt="[PUBLIC_IP_{n:03d}]",
        enabled_default=False,
        description="Public IPv4 addresses. Off by default.",
    ),
    Rule(
        category="ipv6_private",
        finder=find_private_ipv6,
        placeholder_fmt="[PRIVATE_IPV6_{n:03d}]",
        description="Private / loopback / link-local IPv6 addresses (ULA, fe80::, ::1).",
    ),
    Rule(
        category="ipv6_public",
        finder=find_public_ipv6,
        placeholder_fmt="[PUBLIC_IPV6_{n:03d}]",
        enabled_default=False,
        description="Public IPv6 addresses. Off by default.",
    ),
    # secret_token and person_name rules live in secrets.py because they
    # need detect-secrets / spaCy respectively; they're appended to the
    # registry at engine import time.
]
