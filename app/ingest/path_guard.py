"""Shared sensitive-path guard for ingest endpoints and folder watchers.

Returns True if `p` is blocked (should be rejected with 403/400).
Covers: sensitive system dirs, sensitive user dirs, and the Tank DB itself.
"""
from __future__ import annotations

import os
from pathlib import Path


def _blocked_prefixes() -> tuple[Path, ...]:
    home = Path.home()
    return (
        Path("/etc"),
        Path("/proc"),
        Path("/sys"),
        Path("/dev"),
        home / ".ssh",
        home / ".gnupg",
        home / ".aws",
        home / ".tank",
        home / ".config",
    )


def is_blocked_path(p: Path) -> str | None:
    """Return the matched blocked prefix string if `p` is off-limits, else None."""
    resolved = p.resolve()
    for prefix in _blocked_prefixes():
        try:
            resolved.relative_to(prefix)
            return str(prefix)
        except ValueError:
            pass
    return None
