"""Parse intake interview answers and seed entity stubs + Day-1 brief.

Called once after the intake interview is completed. Creates entity stubs
with low confidence (0.3) and provenance='user', tagged with
attrs['stub_source'] = 'intake_interview' so the entity browser can
distinguish them from confirmed (ingested) entities.
"""
from __future__ import annotations

import logging
import re

from app.storage import entities_store, intake_store
from app.role import update_state

log = logging.getLogger("tank.intake_seeder")


def seed_from_answers(interview_id: str, answers: dict) -> list[str]:
    """Create entity stubs from intake answers. Returns list of created entity IDs."""
    created: list[str] = []
    stub_attrs = {"stub_source": "intake_interview", "stub_unconfirmed": True}

    # Q3 — data types
    data_types = answers.get("q3_data_types", [])
    if isinstance(data_types, str):
        data_types = [data_types]
    for dt in data_types:
        if dt and dt.lower() != "none i'm aware of":
            eid = entities_store.upsert_entity(
                type_="Asset",
                name=dt,
                description=f"Data type: {dt}",
                attrs={**stub_attrs, "kind": "data_type"},
                confidence=0.3,
                provenance="user",
            )
            created.append(eid)

    # Q4 — cloud providers
    cloud_providers = answers.get("q4_cloud_providers", [])
    if isinstance(cloud_providers, str):
        cloud_providers = [cloud_providers]
    for cp in cloud_providers:
        if cp and cp.lower() not in ("other", "not sure"):
            eid = entities_store.upsert_entity(
                type_="CloudAccount",
                name=cp,
                description=f"Cloud provider: {cp}",
                attrs={**stub_attrs, "kind": "cloud_provider"},
                confidence=0.3,
                provenance="user",
            )
            created.append(eid)

    # Q5 — services / applications
    services_raw = answers.get("q5_services", "")
    services = _split_names(services_raw)
    for svc in services:
        if svc:
            eid = entities_store.upsert_entity(
                type_="Service",
                name=svc,
                description=f"Service mentioned during intake interview.",
                attrs=stub_attrs,
                confidence=0.3,
                provenance="user",
            )
            created.append(eid)

    # Q6 — teams / service owners
    teams_raw = answers.get("q6_owners", "")
    teams = _split_names(teams_raw)
    for team in teams:
        if team:
            eid = entities_store.upsert_entity(
                type_="Person",   # using Person as a proxy for Team until TeamEntity exists
                name=team,
                description=f"Team or owner mentioned during intake interview.",
                attrs={**stub_attrs, "kind": "team"},
                confidence=0.3,
                provenance="user",
            )
            created.append(eid)

    # Q8 — identity provider
    idp = answers.get("q8_idp", "")
    if isinstance(idp, dict):
        idp = idp.get("name", "") or ""
    if idp and idp.lower() not in ("no", "not sure", ""):
        eid = entities_store.upsert_entity(
            type_="Asset",
            name=idp,
            description="Identity provider (SSO).",
            attrs={**stub_attrs, "kind": "identity_provider"},
            confidence=0.3,
            provenance="user",
        )
        created.append(eid)

    # Q11 — existing security tools
    tools_raw = answers.get("q11_security_tools", "")
    if tools_raw and tools_raw.lower() != "none":
        for tool in _split_names(tools_raw):
            if tool:
                eid = entities_store.upsert_entity(
                    type_="Asset",
                    name=tool,
                    description="Security tool mentioned during intake interview.",
                    attrs={**stub_attrs, "kind": "security_tool"},
                    confidence=0.3,
                    provenance="user",
                )
                created.append(eid)

    intake_store.mark_seeded(interview_id)
    log.info("intake_seeder: created %d entity stubs from interview %s",
             len(created), interview_id)
    return created


def _split_names(raw: str) -> list[str]:
    """Split a freetext comma/newline-separated list of names."""
    if not raw:
        return []
    parts = re.split(r"[,\n;]+", str(raw))
    return [p.strip() for p in parts if p.strip()]
