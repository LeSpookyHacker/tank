"""Nudge generation.

Most nudges are heuristic-driven, not LLM-driven. The LLM-driven ones
(question_of_week, pattern_detection) call Sonnet with the
`nudge_generator.md` prompt.

Rate limit: max 2 NEW open nudges per day (configurable).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from app.claude.event_bus import publish
from app.config import HAIKU_MODEL, MODEL, get_client, load_prompt, log_token_usage
from app.storage import (entities_store, nudges_store, relationships_store,
                         subscriptions_store, usage_store)

log = logging.getLogger("tank.nudges")

_DAILY_CAP = 2


def generate_nudges() -> list[str]:
    """Run all heuristic gates + LLM gates. Return the IDs of nudges
    created in this pass (could be empty)."""
    created: list[str] = []
    if nudges_store.count_open_today() >= _DAILY_CAP:
        log.info("daily nudge cap reached, skipping generation")
        return created

    for fn in (_coverage_gap, _stale_context, _pattern_detection,
               _contradiction, _abandoned_thread,
               _question_of_week, _journal_followup_suggestion,
               _architecture_drift, _decision_expiring,
               _unaddressed_threat, _risk_review_due):
        if nudges_store.count_open_today() >= _DAILY_CAP:
            break
        try:
            nid = fn()
            if nid:
                created.append(nid)
                publish("nudges.global", "nudge_created", {"id": nid})
        except Exception as exc:
            log.warning("nudge generator %s failed: %s",
                        fn.__name__, exc)
    return created


# ---------------- heuristic gates ----------------

def _coverage_gap() -> str | None:
    """Person entities mentioned in KB but with no associated docs."""
    persons = entities_store.list_entities(type_="Person", limit=200)
    no_docs = []
    for p in persons:
        edges = relationships_store.list_for_entity(p["id"], direction="both")
        if not edges:
            no_docs.append(p)
    if not no_docs:
        return None
    sample = no_docs[0]
    return nudges_store.insert(
        kind="coverage_gap",
        title=f"No context on {sample['name']!r}",
        body=f"{sample['name']} appears in your KB but I don't have any "
             f"documents connecting them to a service or team. Worth "
             f"asking them what they work on?",
        payload={"entity_id": sample["id"]},
        priority=60,
    )


def _stale_context() -> str | None:
    """Docs older than 6 months whose related repo has churned."""
    # Cheap heuristic placeholder — we don't have repo-commit dates in
    # the schema. Emit a gentle "review your oldest docs" nudge if any
    # doc is > 180 days old.
    from app.storage.documents_store import list_documents
    docs = list_documents(limit=500)
    if not docs:
        return None
    threshold = time.time() - 180 * 86400
    stale = [d for d in docs if d["ingested_at"] < threshold]
    if not stale:
        return None
    return nudges_store.insert(
        kind="stale_context",
        title=f"{len(stale)} ingested docs are over 6 months old",
        body="Your KB has docs ingested >6 months ago. The underlying "
             "services may have drifted. Worth a re-ingest pass?",
        payload={"doc_count": len(stale)},
        priority=40,
    )


def _pattern_detection() -> str | None:
    """Person mentioned in 3+ chunks but no entity card exists."""
    from app.db import get_conn
    # Find redacted PERSON placeholders (only useful if person_name
    # redaction is enabled). Otherwise look for inferred-low-confidence
    # entities that haven't been linked to enough chunks.
    rows = get_conn().execute(
        "SELECT e.id, e.name, COUNT(DISTINCT ec.chunk_id) AS n "
        "FROM entities e "
        "LEFT JOIN entity_chunks ec ON ec.entity_id = e.id "
        "WHERE e.type = 'Person' AND e.confidence < 0.5 "
        "GROUP BY e.id "
        "HAVING n >= 3 LIMIT 5"
    ).fetchall()
    if not rows:
        return None
    target = rows[0]
    return nudges_store.insert(
        kind="pattern_detection",
        title=f"{target['name']} keeps coming up but I'm not sure who they are",
        body=f"{target['name']} appears across {target['n']} chunks but "
             f"I extracted them with low confidence. Worth confirming "
             f"who they are and what they do?",
        payload={"entity_id": target["id"], "chunk_count": target["n"]},
        priority=55,
    )


def _contradiction() -> str | None:
    """Same logical entity, conflicting attributes across sources.

    Heuristic: find Service entities with multiple `owns` edges pointing
    to different people.
    """
    from app.db import get_conn
    rows = get_conn().execute(
        "SELECT r.dst_id AS service_id, COUNT(DISTINCT r.src_id) AS owner_count "
        "FROM relationships r "
        "WHERE r.kind = 'owns' "
        "GROUP BY r.dst_id "
        "HAVING owner_count > 1 LIMIT 5"
    ).fetchall()
    if not rows:
        return None
    svc_id = rows[0]["service_id"]
    svc = entities_store.get_entity(svc_id)
    if not svc:
        return None
    owners = [
        entities_store.get_entity(r["src_id"])
        for r in relationships_store.list_for_entity(
            svc_id, direction="in", kind="owns",
        )
    ]
    owner_names = [o["name"] for o in owners if o]
    return nudges_store.insert(
        kind="contradiction",
        title=f"Conflicting ownership for {svc['name']!r}",
        body=f"Multiple sources list different owners for {svc['name']}: "
             f"{', '.join(owner_names)}. Which is right?",
        payload={"entity_id": svc_id, "owners": owner_names},
        priority=75,
    )


def _abandoned_thread() -> str | None:
    """Conversations untouched in 14+ days."""
    abandoned = usage_store.abandoned_conversations(days=14)
    if not abandoned:
        return None
    sample = abandoned[0]
    return nudges_store.insert(
        kind="abandoned_thread",
        title=f"Conversation {sample.get('title') or sample['id'][:8]!r} "
              f"has gone quiet",
        body="You haven't returned to this conversation in 14+ days. "
             "Worth a quick recap to close it out — or pick it back up?",
        payload={"conversation_id": sample["id"]},
        priority=30,
    )


# ---------------- LLM-driven gates ----------------

def _question_of_week() -> str | None:
    """3 high-leverage questions to ask this week.

    Fires only Monday mornings. The day-of-week check happens at the
    scheduler level; here we just call the LLM.
    """
    if datetime.now().weekday() != 0:
        return None
    client = get_client()
    try:
        prompt = load_prompt("nudge_generator")
    except FileNotFoundError:
        prompt = "Suggest one high-leverage question the user should ask " \
                 "their manager this week."
    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=512,
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": "Generate the Question of the Week. "
                                  "Return one paragraph only."}],
        )
        log_token_usage("nudges.question_of_week", HAIKU_MODEL, getattr(resp, "usage", None))
        text = ""
        for block in resp.content or []:
            t = getattr(block, "text", None)
            if t:
                text += t
        if not text.strip():
            return None
        return nudges_store.insert(
            kind="question_of_week",
            title="Question of the week",
            body=text.strip(),
            priority=50,
        )
    except Exception as exc:
        log.warning("question_of_week LLM call failed: %s", exc)
        return None


def _journal_followup_suggestion() -> str | None:
    """If today's journal entry surfaces high-confidence followups,
    suggest tracking them."""
    from app.storage.journal_store import get_today
    today = get_today()
    if not today:
        return None
    import json
    try:
        extracted = json.loads(today.get("extracted_json") or "{}")
    except Exception:
        return None
    suggestions = extracted.get("followups", [])
    if not suggestions:
        return None
    return nudges_store.insert(
        kind="journal_followup_suggestion",
        title="Today's journal mentions a possible follow-up",
        body=f"Suggested: {suggestions[0].get('title','(item)')}. "
             f"Track it as a follow-up?",
        payload={"journal_id": today["id"],
                 "suggestion": suggestions[0]},
        priority=45,
    )


# ---------------- Phase 12 gates ----------------

def _architecture_drift() -> str | None:
    """A service's threat model is older than its current arch hash."""
    try:
        from app.claude.threat_modeling import find_drift
    except Exception:
        return None
    drifted = find_drift()
    if not drifted:
        return None
    target = drifted[0]
    return nudges_store.insert(
        kind="architecture_drift",
        title=f"Threat model for {target['service_name']!r} has drifted",
        body=f"The arch chunks for {target['service_name']} have changed "
             f"since v{target['tm_version']} of its threat model was "
             f"generated. Worth regenerating to surface new risks?",
        payload={
            "service_entity_id": target["service_entity_id"],
            "tm_id": target["tm_id"],
        },
        priority=70,
    )


def _decision_expiring() -> str | None:
    """An accepted-risk or deferred-fix decision is about to expire."""
    from app.storage import decisions_store
    expiring = decisions_store.expiring_soon(within_days=7)
    if not expiring:
        return None
    d = expiring[0]
    return nudges_store.insert(
        kind="decision_expiring",
        title=f"Decision expiring: {d['title']!r}",
        body=f"This {d['kind']} expires within 7 days. Reaffirm "
             f"(extend 90 days) or withdraw?",
        payload={"decision_id": d["id"], "kind": d["kind"]},
        priority=65,
    )


def _risk_review_due() -> str | None:
    """A risk register entry is past its scheduled review date."""
    try:
        from app.storage import risks_store
    except Exception:
        return None
    overdue = risks_store.review_overdue()
    if not overdue:
        return None
    r = overdue[0]
    return nudges_store.insert(
        kind="risk_review_due",
        title=f"Risk review overdue: {r['title']!r}",
        body=f"This {r['category']} risk (residual score {r['residual_score']}) "
             f"is past its scheduled review date. Reassess or close it.",
        payload={"risk_id": r["id"], "category": r["category"],
                 "residual_score": r["residual_score"]},
        priority=65,
    )


def _unaddressed_threat() -> str | None:
    """A high-impact / high-likelihood threat in any TM has no
    suggested_controls AND no decision in its scope."""
    from app.storage import decisions_store, threat_models_store
    tms = threat_models_store.list_all_latest()
    for tm in tms:
        threats = tm.get("threats") or []
        for t in threats:
            if t.get("likelihood") == "high" and t.get("impact") == "high":
                if not t.get("suggested_controls"):
                    # Check if there's a decision scoped to this service
                    scoped = decisions_store.list_filtered(
                        scope_entity_id=tm["service_entity_id"],
                    )
                    if not scoped:
                        return nudges_store.insert(
                            kind="unaddressed_threat",
                            title=f"Unaddressed high/high threat: "
                                  f"{t.get('title', 'untitled')}",
                            body=f"Threat in {tm['title']} has no "
                                 f"suggested controls and no decision "
                                 f"in this service's scope. Worth a "
                                 f"design review?",
                            payload={
                                "tm_id": tm["id"],
                                "threat_title": t.get("title"),
                                "service_entity_id": tm["service_entity_id"],
                            },
                            priority=80,
                        )
    return None
