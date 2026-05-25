"""Six report generators sharing a cached scope.

All six use `claude-sonnet-4-6` with adaptive thinking. The scoped
context (entities + linked chunks) is built once per scope and reused
across generators via prompt caching, so a 6-report run is ~2x cheaper
than running each cold.

Each generator returns a Pydantic-typed payload + a markdown rendering;
both get persisted to `reports.content_md_redacted` (audit) and
`content_md` (rehydrated for display).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from app.claude.event_bus import publish
from app.config import MODEL, get_client, load_prompt
from app.kb.entities import get_card, list_by_type
from app.redact.engine import rehydrate
from app.redact.store import load_rehydration_map
from app.role import get_state
from app.schemas import (ControlMatrix, ControlMatrixRow,
                         CrossServiceGapsReport, OnCallHandoff,
                         PlanReport, QuestionList, StakeholderMap,
                         ThreatLandscapeReport, WeeklySecurityDigest)
from app.storage import reports_store

log = logging.getLogger("tank.reports")
T = TypeVar("T", bound=BaseModel)


# ---------------- scope builders ----------------

def _build_scope_block(service_id: str | None = None,
                       limit_per_type: int = 30) -> dict:
    """Cache-controlled text block summarizing the relevant KB slice."""
    parts: list[str] = ["## KB scope"]

    if service_id:
        card = get_card(service_id)
        if card:
            parts.append(f"### Primary service: {card['name']}")
            parts.append(f"description: {card.get('description') or '—'}")
            parts.append(f"attrs: {card.get('attrs')}")
            for ch in card.get("linked_chunks", []):
                parts.append(
                    f"  chunk[{ch['chunk_id']}] section={ch.get('section_path') or '—'}: "
                    f"{(ch.get('snippet') or '')[:300]}"
                )
            parts.append("")

    # Always include a global view of entities by type so reports can
    # reason about the org as a whole.
    for t in ("Service", "Person", "DataStore", "CloudAccount", "Vendor",
              "Control", "Policy", "Runbook", "Repo"):
        rows = list_by_type(t, limit=limit_per_type)
        if not rows:
            continue
        parts.append(f"### {t} ({len(rows)})")
        for r in rows:
            line = f"- [{r['id'][:8]}] {r['name']!r}"
            if r.get("description"):
                line += f" — {(r['description'] or '')[:140]}"
            parts.append(line)
        parts.append("")

    text = "\n".join(parts)
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }


# ---------------- shared runner ----------------

def _run(prompt_name: str, output_format: Type[T], *,
         scope: dict | None = None,
         service_id: str | None = None,
         user_task: str = "") -> tuple[T | None, dict]:
    """Call Claude with the prompt + scope. Returns (parsed, usage)."""
    client = get_client()
    system_block = {
        "type": "text",
        "text": load_prompt(prompt_name),
        "cache_control": {"type": "ephemeral"},
    }
    scope_block = _build_scope_block(service_id=service_id)
    user_blocks = [scope_block]
    if user_task:
        user_blocks.append({"type": "text", "text": user_task})
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=[system_block],
            messages=[{"role": "user", "content": user_blocks}],
            output_format=output_format,
        )
        parsed = getattr(resp, "parsed_output", None)
        usage = getattr(resp, "usage", None)
        usage_d = {}
        if usage:
            usage_d = {
                "tokens_in": getattr(usage, "input_tokens", 0) or 0,
                "tokens_out": getattr(usage, "output_tokens", 0) or 0,
                "cache_read_in": getattr(usage, "cache_read_input_tokens", 0) or 0,
                "cache_create_in": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            }
        return parsed, usage_d
    except Exception as exc:
        log.warning("report %s failed: %s", prompt_name, exc)
        return None, {}


# ---------------- markdown rendering ----------------

def _render_threat(report: ThreatLandscapeReport) -> str:
    lines = [f"# Threat landscape — {report.service_name}", "",
             report.summary, ""]
    for t in report.threats:
        lines.append(f"## {t.stride_category}: {t.title}")
        lines.append(f"- Likelihood: **{t.likelihood}** · Impact: **{t.impact}**")
        lines.append("")
        lines.append(t.description)
        if t.suggested_controls:
            lines.append("")
            lines.append("**Suggested controls:**")
            for c in t.suggested_controls:
                lines.append(f"- {c}")
        if t.evidence_chunk_ids:
            lines.append("")
            lines.append(f"_evidence: {', '.join(t.evidence_chunk_ids)}_")
        lines.append("")
    if report.blind_spots:
        lines.append("## Blind spots")
        for b in report.blind_spots:
            lines.append(f"- {b}")
    return "\n".join(lines)


def _render_gaps(report: CrossServiceGapsReport) -> str:
    lines = ["# Cross-service gaps & blind spots", "", report.summary, ""]
    for g in report.gaps:
        lines.append(f"## {g.pattern} _({g.severity})_")
        lines.append(g.notes)
        if g.affected_entity_names:
            lines.append("")
            lines.append(f"_affects: {', '.join(g.affected_entity_names)}_")
        if g.evidence_chunk_ids:
            lines.append(f"_evidence: {', '.join(g.evidence_chunk_ids)}_")
        lines.append("")
    if report.blind_spots:
        lines.append("## Blind spots")
        for b in report.blind_spots:
            lines.append(f"- {b}")
    return "\n".join(lines)


def _render_plan(report: PlanReport) -> str:
    lines = ["# 30 / 60 / 90 day plan", "", report.rationale, ""]
    for window, actions in (("Day 30", report.day_30),
                            ("Day 60", report.day_60),
                            ("Day 90", report.day_90)):
        lines.append(f"## {window}")
        for a in actions:
            lines.append(f"### {a.title}")
            lines.append(f"- **Why:** {a.why}")
            lines.append(f"- **Effort:** {a.estimated_effort}")
            lines.append(f"- **Success signal:** {a.success_signal}")
            if a.who_to_talk_to:
                lines.append(f"- **Who to talk to:** {', '.join(a.who_to_talk_to)}")
            lines.append("")
    return "\n".join(lines)


def _render_stakeholder(report: StakeholderMap) -> str:
    lines = ["# Stakeholder map", "", report.summary, ""]
    for tier, label in (("critical", "Critical"),
                        ("frequent", "Frequent"),
                        ("situational", "Situational")):
        items = getattr(report, tier)
        if not items:
            continue
        lines.append(f"## {label}")
        for s in items:
            line = f"- **{s.name}**"
            if s.role:
                line += f" — {s.role}"
            lines.append(line)
            if s.overlap_areas:
                lines.append(f"  - overlap: {', '.join(s.overlap_areas)}")
            if s.suggested_first_conversation:
                lines.append(f"  - first chat: {s.suggested_first_conversation}")
        lines.append("")
    if report.first_30_day_intros:
        lines.append("## First 30-day intro list")
        for x in report.first_30_day_intros:
            lines.append(f"- {x}")
    return "\n".join(lines)


def _render_questions(report: QuestionList) -> str:
    lines = [f"# Questions for {report.team_or_person}", ""]
    for label, items in (("Must ask", report.must_ask),
                         ("Should ask", report.should_ask),
                         ("Nice to ask", report.nice_to_ask),
                         ("Red flags to probe", report.red_flags_to_probe)):
        if not items:
            continue
        lines.append(f"## {label}")
        for q in items:
            lines.append(f"- {q}")
        lines.append("")
    return "\n".join(lines)


def _render_matrix(report: ControlMatrix) -> str:
    lines = ["# Control coverage matrix", "", report.summary, ""]
    controls = report.controls_checked
    if controls and report.rows:
        header = "| Service | " + " | ".join(controls) + " |"
        sep = "|" + "|".join(["---"] * (len(controls) + 1)) + "|"
        lines.append(header)
        lines.append(sep)
        for row in report.rows:
            vals = []
            for c in controls:
                v = row.controls.get(c, "unknown")
                symbol = {"yes": "✓", "partial": "~", "no": "✗",
                          "unknown": "?"}.get(v, "?")
                vals.append(symbol)
            lines.append(f"| {row.service_name} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


# ---------------- public generators ----------------

def _finalize(*, kind: str, title: str, content_md_redacted: str,
              usage: dict, scope: dict | None = None) -> str:
    """Rehydrate, persist, publish event. Returns report_id."""
    mapping = load_rehydration_map()
    content_md = rehydrate(content_md_redacted, mapping)
    state = get_state()
    rid = reports_store.insert(
        kind=kind, title=title,
        content_md=content_md,
        content_md_redacted=content_md_redacted,
        role_mode=state.role_mode.value,
        model=MODEL,
        scope=scope,
        tokens_in=usage.get("tokens_in"),
        tokens_out=usage.get("tokens_out"),
        cache_read_in=usage.get("cache_read_in"),
        cache_create_in=usage.get("cache_create_in"),
    )
    publish("reports.global", "report_created",
            {"id": rid, "kind": kind, "title": title})
    return rid


def threat_landscape(service_id: str) -> str:
    parsed, usage = _run("report_threat_landscape", ThreatLandscapeReport,
                         service_id=service_id,
                         user_task="Produce a STRIDE-style threat landscape "
                                   "for the primary service. Use evidence "
                                   "chunk IDs you saw in scope.")
    if parsed is None:
        raise RuntimeError("threat_landscape generation returned no output")
    md = _render_threat(parsed)
    return _finalize(kind="threat_landscape",
                     title=f"Threat landscape — {parsed.service_name}",
                     content_md_redacted=md, usage=usage,
                     scope={"service_id": service_id})


def cross_service_gaps() -> str:
    parsed, usage = _run("report_cross_service_gaps", CrossServiceGapsReport,
                         user_task="Produce a cross-service gaps report.")
    if parsed is None:
        raise RuntimeError("cross_service_gaps generation returned no output")
    md = _render_gaps(parsed)
    return _finalize(kind="cross_service_gaps",
                     title="Cross-service gaps & blind spots",
                     content_md_redacted=md, usage=usage)


def plan_30_60_90() -> str:
    parsed, usage = _run("report_30_60_90", PlanReport,
                         user_task="Produce a 30/60/90-day plan tailored "
                                   "to the user's scope.")
    if parsed is None:
        raise RuntimeError("30/60/90 plan generation returned no output")
    md = _render_plan(parsed)
    return _finalize(kind="plan_30_60_90",
                     title="30 / 60 / 90 day plan",
                     content_md_redacted=md, usage=usage)


def stakeholder_map() -> str:
    parsed, usage = _run("report_stakeholder_map", StakeholderMap,
                         user_task="Produce a stakeholder map.")
    if parsed is None:
        raise RuntimeError("stakeholder_map generation returned no output")
    md = _render_stakeholder(parsed)
    return _finalize(kind="stakeholder_map", title="Stakeholder map",
                     content_md_redacted=md, usage=usage)


def questions_for(team_or_person: str) -> str:
    parsed, usage = _run(
        "report_questions_for_team", QuestionList,
        user_task=f"Produce a ranked question list for "
                  f"interacting with: {team_or_person}",
    )
    if parsed is None:
        raise RuntimeError("questions_for generation returned no output")
    md = _render_questions(parsed)
    return _finalize(kind="questions_for_team",
                     title=f"Questions for {team_or_person}",
                     content_md_redacted=md, usage=usage,
                     scope={"team_or_person": team_or_person})


def control_matrix() -> str:
    parsed, usage = _run("report_control_matrix", ControlMatrix,
                         user_task="Produce a control coverage matrix "
                                   "across services in scope.")
    if parsed is None:
        raise RuntimeError("control_matrix generation returned no output")
    md = _render_matrix(parsed)
    return _finalize(kind="control_matrix",
                     title="Control coverage matrix",
                     content_md_redacted=md, usage=usage)


def _render_oncall_handoff(report: OnCallHandoff) -> str:
    lines = [f"# On-call handoff — {report.service_name}", "",
             report.notes, ""]
    if report.on_call_now:
        lines.append(f"_On call now: {report.on_call_now}_")
        lines.append("")
    if report.deploy_freeze:
        lines.append(f"**Deploy freeze:** {report.deploy_freeze}")
        lines.append("")
    if report.open_action_items:
        lines.append("## Open action items")
        for x in report.open_action_items:
            lines.append(f"- [ ] {x}")
        lines.append("")
    if report.recent_incidents:
        lines.append("## Recent incidents (30d)")
        for x in report.recent_incidents:
            lines.append(f"- {x}")
        lines.append("")
    if report.new_threats:
        lines.append("## New threats since last TM")
        for x in report.new_threats:
            lines.append(f"- {x}")
    return "\n".join(lines)


def _render_weekly_digest(report: WeeklySecurityDigest) -> str:
    lines = [f"# {report.week_label}", "",
             f"**This week's headline:** {report.one_thing_to_focus}", ""]
    for sec in report.sections:
        lines.append(f"## {sec.title}")
        for b in sec.bullets:
            lines.append(f"- {b}")
        lines.append("")
    return "\n".join(lines)


def oncall_handoff(service_id: str) -> str:
    parsed, usage = _run("report_oncall_handoff", OnCallHandoff,
                         service_id=service_id,
                         user_task="Produce a per-service on-call "
                                   "handoff brief for the engineer about "
                                   "to take the pager.")
    if parsed is None:
        raise RuntimeError("oncall_handoff returned no output")
    md = _render_oncall_handoff(parsed)
    return _finalize(kind="oncall_handoff",
                     title=f"On-call handoff — {parsed.service_name}",
                     content_md_redacted=md, usage=usage,
                     scope={"service_id": service_id})


def weekly_security_digest() -> str:
    parsed, usage = _run("report_weekly_security_digest", WeeklySecurityDigest,
                         user_task="Produce the weekly security digest "
                                   "summarizing this past week's activity.")
    if parsed is None:
        raise RuntimeError("weekly_security_digest returned no output")
    md = _render_weekly_digest(parsed)
    return _finalize(kind="weekly_security_digest",
                     title=parsed.week_label or "Weekly security digest",
                     content_md_redacted=md, usage=usage)


def attack_mapping() -> str:
    """ATT&CK mapping report: threats × technique × detection coverage."""
    from app.claude.attack_mapping import generate as _gen
    parsed = _gen()
    if not parsed.rows:
        raise RuntimeError("attack_mapping returned no rows")
    lines = ["# ATT&CK mapping", "", parsed.coverage_summary, ""]
    if parsed.top_gaps:
        lines.append("## Top gaps (exposed but uncovered)")
        for g in parsed.top_gaps:
            lines.append(f"- {g}")
        lines.append("")
    lines.append("| Service | Tactic | Technique | Exposure | Detections |")
    lines.append("|---|---|---|---|---|")
    for r in parsed.rows:
        det = ", ".join(r.detections) if r.detections else "—"
        lines.append(f"| {r.service_name} | {r.tactic} | "
                     f"{r.technique_id} {r.technique_name} | "
                     f"{r.exposure} | {det} |")
    md = "\n".join(lines)
    return _finalize(kind="attack_mapping",
                     title="ATT&CK mapping",
                     content_md_redacted=md, usage={})


def iam_audit() -> str:
    """IAM audit report over all ingested IAMPolicy entities."""
    from app.claude.iam_translator import audit as _audit
    parsed = _audit()
    lines = ["# IAM audit", "", parsed.summary, ""]
    if parsed.top_risks:
        lines.append("## Critical (score ≥ 7)")
        for n in parsed.top_risks:
            lines.append(f"- {n}")
        lines.append("")
    lines.append("## Policies")
    for p in parsed.policies:
        lines.append(f"### {p.policy_name} — score {p.score:.1f}")
        lines.append(p.explanation_md)
        if p.risks:
            for r in p.risks:
                lines.append(f"  - {r}")
        lines.append("")
    md = "\n".join(lines)
    return _finalize(kind="iam_audit",
                     title="IAM audit",
                     content_md_redacted=md, usage={})


REPORT_REGISTRY = {
    "threat_landscape": threat_landscape,
    "cross_service_gaps": cross_service_gaps,
    "plan_30_60_90": plan_30_60_90,
    "stakeholder_map": stakeholder_map,
    "questions_for_team": questions_for,
    "control_matrix": control_matrix,
    "oncall_handoff": oncall_handoff,
    "weekly_security_digest": weekly_security_digest,
    "attack_mapping": attack_mapping,
    "iam_audit": iam_audit,
}
