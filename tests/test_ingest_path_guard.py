"""Tests for app/ingest/path_guard.py (FIX-1 — sensitive-path blocklist).

path_guard has no app-level dependencies (stdlib only), so we import it
directly rather than going through app.ingest.__init__ (which would drag in
pipeline.py and the anthropic SDK).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Import path_guard directly without triggering app/ingest/__init__.py.
_spec = importlib.util.spec_from_file_location(
    "path_guard",
    Path(__file__).parent.parent / "app" / "ingest" / "path_guard.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["path_guard"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
is_blocked_path = _mod.is_blocked_path

import pytest


def _p(s: str) -> Path:
    return Path(s).expanduser()


@pytest.mark.parametrize("path_str", [
    "~/.ssh/id_rsa",
    "~/.ssh",
    "~/.gnupg",
    "~/.aws/credentials",
    "~/.aws",
    "~/.tank/db.sqlite",
    "~/.tank",
    "~/.config",
    "/etc/passwd",
    "/etc/shadow",
    "/proc/1/mem",
    "/sys/kernel",
    "/dev/sda",
])
def test_blocked_paths(path_str: str) -> None:
    p = _p(path_str)
    result = is_blocked_path(p)
    assert result is not None, f"Expected {path_str!r} to be blocked, got None"


@pytest.mark.parametrize("path_str", [
    "~/documents/architecture.md",
    "~/projects/myrepo",
    "~/Desktop/report.pdf",
    "/tmp/upload-1234",
])
def test_allowed_paths(path_str: str) -> None:
    p = _p(path_str)
    result = is_blocked_path(p)
    assert result is None, f"Expected {path_str!r} to be allowed, got {result!r}"
