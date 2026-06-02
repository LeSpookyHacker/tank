"""Tests for the service ownership / on-call roster (Part B).

Covers `ownership_store` CRUD + graph seeding and the new nav/page
routes returning 200. Uses the `fresh_db` fixture so each test gets an
isolated SQLite DB.
"""
from __future__ import annotations

import pytest


def _seed_service_and_person(db):
    from app.storage import entities_store
    pid = entities_store.upsert_entity(type_="Person", name="Alice Ops",
                                        provenance="user")
    sid = entities_store.upsert_entity(type_="Service", name="auth-service",
                                       provenance="user")
    return sid, pid


def test_ownership_store_crud(fresh_db):
    from app.storage import ownership_store
    sid, pid = _seed_service_and_person(fresh_db)

    assert ownership_store.get(sid) is None

    ownership_store.set_owner(
        entity_id=sid,
        primary_owner_entity_id=pid,
        on_call_contact="#sec-oncall",
        escalation=[{"level": "L1", "contact": "on-call eng"}],
        provenance="user",
    )
    row = ownership_store.get(sid)
    assert row is not None
    assert row["primary_owner_entity_id"] == pid
    assert row["on_call_contact"] == "#sec-oncall"
    assert row["escalation"] == [{"level": "L1", "contact": "on-call eng"}]
    assert row["provenance"] == "user"

    assert any(r["entity_id"] == sid for r in ownership_store.list_all())

    ownership_store.clear(sid)
    assert ownership_store.get(sid) is None


def test_seed_from_graph_proposes_owner(fresh_db):
    from app.storage import (entities_store, ownership_store,
                             relationships_store)
    sid, pid = _seed_service_and_person(fresh_db)
    relationships_store.upsert_relationship(
        src_id=pid, dst_id=sid, kind="manages", provenance="source",
    )
    seeded = ownership_store.seed_from_graph(sid)
    assert seeded is not None
    assert seeded["primary_owner_entity_id"] == pid
    assert seeded["provenance"] == "inferred"


def test_on_call_control_gap_consults_roster(fresh_db):
    from app.kb.tools import execute_tool
    from app.storage import ownership_store
    sid, pid = _seed_service_and_person(fresh_db)

    # No roster entry yet → counted as a gap.
    res = execute_tool("find_control_gaps", {"control": "on_call"})
    assert res["gap_count"] == 1

    ownership_store.set_owner(entity_id=sid, on_call_contact="#sec-oncall",
                              provenance="user")
    res2 = execute_tool("find_control_gaps", {"control": "on_call"})
    assert res2["gap_count"] == 0


@pytest.mark.parametrize("path", ["/journal", "/followups", "/cadence",
                                  "/ownership"])
def test_companion_pages_render(fresh_db, path):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get(path).status_code == 200


def test_front_door_is_today_home(fresh_db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        # Before onboarding, the front door gates to the onboarding flow.
        pre = c.get("/", follow_redirects=False)
        assert pre.status_code == 302
        assert pre.headers["location"] == "/onboarding"

        # Drive onboarding through the app's own API (shares the app's DB
        # connection) so the gate opens.
        c.post("/api/onboarding/skip")

        r = c.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert "Today's digest" in r.text
        # Workspaces console stays distinct (no `/` → `/dashboard` redirect).
        assert c.get("/dashboard", follow_redirects=False).status_code == 200
