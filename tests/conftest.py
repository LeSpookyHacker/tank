"""Pytest fixtures.

Every test gets a fresh SQLite DB at a tmp_path so state doesn't leak
between tests. We patch the TANK_DB_PATH env var BEFORE app.db is
imported, which is enforced by import order in the test modules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "db.sqlite"
    monkeypatch.setenv("TANK_DB_PATH", str(db_file))

    # Drop any cached module-level state so the new env var takes effect.
    for mod_name in list(sys.modules):
        if mod_name == "app.db" or mod_name.startswith("app.db."):
            del sys.modules[mod_name]
        if mod_name.startswith("app.redact"):
            del sys.modules[mod_name]
        if mod_name == "app.role":
            del sys.modules[mod_name]

    # Reset the module-level _CONN if it was already established.
    import app.db as db_mod
    db_mod._CONN = None

    yield db_file
    db_mod._CONN = None
