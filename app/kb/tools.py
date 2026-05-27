"""Anthropic tool-use schemas + local dispatch table for the chat loop.

Tools available to the chat assistant:
- search_kb        — hybrid retrieval over chunks
- get_entity       — full entity card by id or (type, name)
- list_relationships — outgoing/incoming edges
- find_control_gaps  — services that lack a given control family
- list_entities    — pagination by type
- get_document     — document metadata + optional chunks

Tool results are already-redacted (chunks were redacted at ingest).
A defense-in-depth `apply_redactions` pass runs in chat.py before
serializing the result back to Claude.
"""
from __future__ import annotations

from typing import Any

from app.kb import entities as kb_entities
from app.kb import relationships as kb_relationships
from app.kb.search import hybrid_search
from app.storage import documents_store, entities_store


# ---------------- schemas ----------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_kb",
        "description": (
            "Hybrid (vector + BM25) search over redacted chunks of "
            "ingested docs. Use this whenever you need to ground a "
            "claim in something the user actually has."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Natural-language query."},
                "type_filter": {
                    "type": "string",
                    "description": (
                        "Optional. One of: Service, Repo, Person, "
                        "Endpoint, DataStore, CloudAccount, Vendor, "
                        "Control, Policy, Runbook. Restricts results "
                        "to chunks that mention an entity of that type."
                    ),
                },
                "top_k": {"type": "integer", "default": 10,
                          "minimum": 1, "maximum": 25},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_entity",
        "description": (
            "Fetch a full entity card (description, attrs, linked chunks, "
            "edge count). Look up by id OR by (type, name)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "type": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "list_relationships",
        "description": (
            "Get edges around an entity. Pass entity_id, direction, "
            "and optionally a kind filter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "direction": {"type": "string",
                              "enum": ["out", "in", "both"],
                              "default": "both"},
                "kind": {"type": "string",
                         "description": (
                             "Optional. One of: depends_on, owns, "
                             "reports_to, stores_data_in, "
                             "authenticates_via, exposes, hosted_in, "
                             "integrates_with, has_control."
                         )},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "find_control_gaps",
        "description": (
            "Find services that lack a given control (e.g. 'sso', "
            "'mfa', 'secrets_mgmt', 'on_call', 'threat_model_on_file')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "control": {"type": "string"},
                "scope_entity_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional. Restrict to these services.",
                },
            },
            "required": ["control"],
        },
    },
    {
        "name": "list_entities",
        "description": "Paginated list of entities filtered by type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "limit": {"type": "integer", "default": 50,
                          "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
            },
            "required": ["type"],
        },
    },
    {
        "name": "get_document",
        "description": "Document metadata; chunks optional (token-heavy).",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "include_chunks": {"type": "boolean", "default": False},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "get_threat_model",
        "description": (
            "Fetch the latest threat model for a service. Returns the "
            "frozen STRIDE threats, summary, and arch_snapshot_hash. "
            "Use when the user asks about threats / risks for a specific "
            "service."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "service_name": {"type": "string"},
            },
        },
    },
    {
        "name": "find_decisions",
        "description": (
            "Search the decisions log. Filter by kind "
            "(design_choice|accepted_risk|deferred_fix|security_invariant), "
            "status (open|withdrawn|expired|reaffirmed), or scope entity. "
            "Use when the user asks 'why did we…' or 'what did we decide…'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "status": {"type": "string", "default": "open"},
                "scope_entity_id": {"type": "string"},
                "limit": {"type": "integer", "default": 25, "maximum": 100},
            },
        },
    },
    {
        "name": "get_recent_decisions",
        "description": (
            "List decisions made in the last N days. Use for "
            "'what's been decided lately' or weekly-digest style queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30,
                         "minimum": 1, "maximum": 365},
            },
        },
    },
    {
        "name": "find_detection_for_technique",
        "description": (
            "Return Detection entities that cover a MITRE ATT&CK "
            "technique (e.g. T1078). Use when the user asks 'do we "
            "detect X?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "attack_id": {"type": "string",
                              "description": "ATT&CK technique ID, e.g. T1078"},
            },
            "required": ["attack_id"],
        },
    },
    {
        "name": "find_iam_risks",
        "description": (
            "Surface IAMPolicy entities ranked by risk score. Use for "
            "'which of our IAM policies are risky' style questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10,
                          "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "find_evidence_for_control",
        "description": (
            "Return ingested evidence (documents, decisions, policies, "
            "runbooks, threat models) that maps to a control_id. Use for "
            "compliance / audit questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "control_id": {"type": "string"},
            },
            "required": ["control_id"],
        },
    },
    {
        "name": "search_lessons",
        "description": (
            "Search the lessons-learned database (from postmortems, "
            "tabletops, design reviews). Use when the user asks 'has "
            "this happened before' or 'what did we learn about…'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "tag": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_ir_runbooks",
        "description": (
            "Return IR runbooks, optionally filtered by service. "
            "Use when the user asks 'what's the runbook for X' or "
            "'what do we do if Y happens'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string"},
                "service_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10,
                          "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "get_risk_register",
        "description": (
            "Return entries from the risk register, optionally filtered "
            "by category (data_breach|availability|supply_chain|"
            "access_control|regulatory|ai_model_abuse|insider_threat|"
            "third_party|infrastructure|application|other) or treatment "
            "(mitigate|accept|transfer|avoid). Use when the user asks "
            "'what are our top risks' or 'show me the risk register'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "treatment": {"type": "string"},
                "limit": {"type": "integer", "default": 25,
                          "minimum": 1, "maximum": 100},
            },
        },
    },
]


# ---------------- dispatch ----------------

def execute_tool(name: str, args: dict[str, Any]) -> dict | list:
    """Execute a tool call locally. Returns JSON-serializable output."""
    if name == "search_kb":
        hits = hybrid_search(
            str(args.get("query", ""))[:500],
            k=max(1, min(25, int(args.get("top_k", 10)))),
            type_filter=args.get("type_filter"),
        )
        return {
            "hits": [
                {
                    "chunk_id": h.chunk_id,
                    "document_id": h.document_id,
                    "section_path": h.section_path,
                    "snippet": h.snippet,
                    "score": round(h.score, 4),
                    "source": h.source,
                }
                for h in hits
            ],
        }

    if name == "get_entity":
        if "entity_id" in args and args["entity_id"]:
            card = kb_entities.get_card(args["entity_id"])
        elif args.get("type") and args.get("name"):
            card = kb_entities.find_by_name(args["type"], args["name"])
        else:
            return {"error": "must supply entity_id or (type+name)"}
        return card or {"error": "not found"}

    if name == "list_relationships":
        return kb_relationships.traverse(
            args["entity_id"],
            direction=args.get("direction", "both"),
            kind=args.get("kind"),
            hops=1,
        )

    if name == "find_control_gaps":
        return _find_control_gaps(
            args["control"],
            scope=args.get("scope_entity_ids"),
        )

    if name == "list_entities":
        return {
            "entities": kb_entities.list_by_type(
                args["type"], limit=int(args.get("limit", 50)),
            ),
        }

    if name == "get_document":
        doc = documents_store.get_document(args["document_id"])
        if not doc:
            return {"error": "not found"}
        out = dict(doc)
        if args.get("include_chunks"):
            from app.storage.chunks_store import list_chunks_for_doc
            chunks = list_chunks_for_doc(args["document_id"])
            out["chunks"] = [
                {
                    "id": c["id"],
                    "ordinal": c["ordinal"],
                    "section_path": c["section_path"],
                    "text_redacted": c["text_redacted"],
                    "token_count": c["token_count"],
                }
                for c in chunks
            ]
        return out

    if name == "get_threat_model":
        from app.storage import threat_models_store
        sid = args.get("service_id")
        if not sid and args.get("service_name"):
            card = kb_entities.find_by_name("Service", args["service_name"])
            if card:
                sid = card["id"]
        if not sid:
            return {"error": "must supply service_id or service_name"}
        tm = threat_models_store.latest_for_service(sid)
        if not tm:
            return {"error": "no threat model for this service",
                    "service_id": sid}
        return {
            "id": tm["id"], "version": tm["version"],
            "title": tm["title"],
            "threats": tm["threats"],
            "body_md_redacted": tm["body_md_redacted"],
            "arch_snapshot_hash": tm["arch_snapshot_hash"],
            "generated_at": tm["generated_at"],
        }

    if name == "find_decisions":
        from app.storage import decisions_store
        rows = decisions_store.list_filtered(
            kind=args.get("kind"),
            status=args.get("status", "open"),
            scope_entity_id=args.get("scope_entity_id"),
            limit=int(args.get("limit", 25)),
        )
        return {"decisions": [
            {"id": d["id"], "title": d["title"], "kind": d["kind"],
             "status": d["status"], "body_md_redacted": d["body_md_redacted"],
             "rationale": d.get("rationale"),
             "expires_at": d.get("expires_at")}
            for d in rows
        ]}

    if name == "get_recent_decisions":
        from app.storage import decisions_store
        rows = decisions_store.recent(days=int(args.get("days", 30)))
        return {"decisions": [
            {"id": d["id"], "title": d["title"], "kind": d["kind"],
             "status": d["status"], "created_at": d["created_at"]}
            for d in rows
        ]}

    if name == "find_detection_for_technique":
        from app.kb import detections as detections_helper
        return detections_helper.find_for_technique(args["attack_id"])

    if name == "find_iam_risks":
        from app.kb import iam as iam_helper
        return iam_helper.find_risks(limit=int(args.get("limit", 10)))

    if name == "find_evidence_for_control":
        from app.kb import compliance as compliance_helper
        return compliance_helper.find_evidence(args["control_id"])

    if name == "search_lessons":
        from app.storage import lessons_store
        return {"lessons": lessons_store.search(
            args["query"], tag=args.get("tag"), limit=20,
        )}

    if name == "find_ir_runbooks":
        from app.storage import ir_runbooks_store
        sid = args.get("service_id")
        if not sid and args.get("service_name"):
            card = kb_entities.find_by_name("Service", args["service_name"])
            if card:
                sid = card["id"]
        rows = ir_runbooks_store.list_all(
            service_entity_id=sid,
            limit=int(args.get("limit", 10)),
        )
        return {"runbooks": [
            {"id": r["id"],
             "threat_scenario": r["threat_scenario"],
             "severity_trigger": r["severity_trigger"],
             "confirmed": bool(r.get("confirmed_by_user")),
             "generated_at": r["generated_at"]}
            for r in rows
        ]}

    if name == "get_risk_register":
        from app.storage import risks_store
        from app.storage import entities_store as _es
        rows = risks_store.list_all(
            status="open",
            category=args.get("category"),
            limit=int(args.get("limit", 25)),
        )
        treatment_filter = args.get("treatment")
        if treatment_filter:
            rows = [r for r in rows if r.get("treatment") == treatment_filter]
        out = []
        for r in rows:
            owner_name = None
            if r.get("owner_entity_id"):
                ent = _es.get_entity(r["owner_entity_id"])
                if ent:
                    owner_name = ent["name"]
            out.append({
                "id": r["id"], "title": r["title"],
                "category": r["category"],
                "inherent_score": r["inherent_score"],
                "residual_score": r["residual_score"],
                "treatment": r["treatment"],
                "status": r["status"],
                "owner": owner_name,
            })
        return {"risks": out, "count": len(out)}

    return {"error": f"unknown tool: {name}"}


def _find_control_gaps(control: str, scope: list[str] | None) -> dict:
    """Return services in scope (or all services) that lack a
    `has_control` edge to a Control entity matching `control`.
    """
    control_norm = control.strip().lower().replace(" ", "_").replace("-", "_")
    services = entities_store.list_entities(type_="Service", limit=500)
    if scope:
        services = [s for s in services if s["id"] in set(scope)]

    gaps = []
    for s in services:
        edges = kb_relationships.traverse(s["id"], direction="out",
                                          kind="has_control")["edges"]
        has = False
        for edge in edges:
            other = entities_store.get_entity(edge["dst_id"])
            if not other:
                continue
            other_norm = (other["name"] or "").lower().replace(" ", "_").replace("-", "_")
            if control_norm in other_norm:
                has = True
                break
        if not has:
            gaps.append({"id": s["id"], "name": s["name"]})

    return {"control": control, "gap_count": len(gaps), "services": gaps}
