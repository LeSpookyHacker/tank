"""Six report generators sharing a cached scope.

All six use `claude-sonnet-4-6` with structured output. The scoped
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
import re
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from app.claude.caching import CACHE_1H, build_scope_block
from app.claude.event_bus import publish
from app.config import MODEL, get_client, load_prompt
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.role import get_state
from app.schemas import (ControlMatrix, ControlMatrixRow,
                         CrossServiceGapsReport, OnCallHandoff,
                         InitialAssessmentReport, PlanReport, ProgramRoadmapReport,
                         QuestionList, RiskRegisterReport, StateOfSecurityReport,
                         StakeholderMap, ThreatLandscapeReport,
                         WeeklySecurityDigest)
from app.storage import reports_store

log = logging.getLogger("tank.reports")
T = TypeVar("T", bound=BaseModel)

_PH_RE = re.compile(
    r"\[(?:EMAIL|INTERNAL_HOST|HOST|PRIVATE_IP|PUBLIC_IP|"
    r"AWS_ACCT|AWS_ARN|GCP_PROJECT|AZURE_SUB|SECRET|PERSON|CUSTOM[A-Z_]*)_\d+\]"
)


def _ph_in(text: str) -> set[str]:
    return set(_PH_RE.findall(text or ""))


# ---------------- scope builders ----------------

# Back-compat re-export. The canonical implementation lives in
# `app/claude/caching.py` so non-report modules (anniversaries, policy,
# day1, plan, meeting prep, prioritization, compliance wizard) share the
# same cached block and benefit from cross-module cache hits.
def _build_scope_block(service_id: str | None = None,
                       limit_per_type: int = 30) -> dict:
    return build_scope_block(service_id=service_id, limit_per_type=limit_per_type)


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
        # Each report's system prompt is stable; 1h cache covers
        # any digest-time burst that re-runs the same kind.
        "cache_control": CACHE_1H,
    }
    scope_block = build_scope_block(service_id=service_id)
    user_blocks = [scope_block]
    if user_task:
        user_blocks.append({"type": "text", "text": user_task})
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=8192,
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
    mapping = load_rehydration_map(_ph_in(content_md_redacted))
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
    redacted_who = apply_redactions(team_or_person).redacted_text
    parsed, usage = _run(
        "report_questions_for_team", QuestionList,
        user_task=f"Produce a ranked question list for "
                  f"interacting with: {redacted_who}",
    )
    if parsed is None:
        raise RuntimeError("questions_for generation returned no output")
    md = _render_questions(parsed)
    return _finalize(kind="questions_for_team",
                     title=f"Questions for {redacted_who}",
                     content_md_redacted=md, usage=usage,
                     scope={"team_or_person": redacted_who})


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


def _build_risk_register_user_task() -> str:
    """Build the risk-register user-task block from the current DB state.

    Shared by `risk_register()` (sync) and the batched path so both see
    the same set of open risks at submission time.
    """
    from app.storage import risks_store as rs
    from app.storage import entities_store

    risks = rs.list_all(status="open", limit=100)
    context_lines = ["## Current risk register entries"]
    for r in risks:
        owner_name = "unassigned"
        if r.get("owner_entity_id"):
            ent = entities_store.get_entity(r["owner_entity_id"])
            if ent:
                owner_name = apply_redactions(ent["name"]).redacted_text
        redacted_title = apply_redactions(r["title"]).redacted_text
        context_lines.append(
            f"- [{r['category']}] {redacted_title} | inherent={r['inherent_score']} "
            f"residual={r['residual_score']} treatment={r['treatment']} owner={owner_name}"
        )
    return "\n".join(context_lines) + "\n\nProduce the risk register report."


def _render_risk_register(parsed: RiskRegisterReport) -> str:
    lines = ["# Risk register", "", parsed.summary, ""]
    if parsed.top_risks:
        lines.append("## Critical risks (residual score ≥ 12)")
        for r in parsed.top_risks:
            lines.append(f"- {r}")
        lines.append("")
    if parsed.risks:
        lines.append("| Risk | Category | Inherent | Residual | Treatment | Owner |")
        lines.append("|---|---|---|---|---|---|")
        for r in parsed.risks:
            lines.append(
                f"| {r.get('title','?')} | {r.get('category','?')} | "
                f"{r.get('inherent_score','?')} | {r.get('residual_score','?')} | "
                f"{r.get('treatment','?')} | {r.get('owner','?')} |"
            )
        lines.append("")
    if parsed.control_coverage_notes:
        lines.append("## Control coverage notes")
        for n in parsed.control_coverage_notes:
            lines.append(f"- {n}")
    return "\n".join(lines)


def risk_register() -> str:
    """Risk register report — ranked by residual score with coverage notes."""
    parsed, usage = _run(
        "report_risk_register", RiskRegisterReport,
        user_task=_build_risk_register_user_task(),
    )
    if parsed is None:
        raise RuntimeError("risk_register generation returned no output")
    md = _render_risk_register(parsed)
    return _finalize(kind="risk_register", title="Risk register",
                     content_md_redacted=md, usage=usage)


def _render_state_of_security(r: StateOfSecurityReport) -> str:
    lines = ["# State of Security — Monthly Brief", "", r.program_health_summary, ""]
    if r.top_risks:
        lines.append("## Active risks")
        for risk in r.top_risks[:3]:
            lines.append(f"### {risk.get('title', '?')}")
            lines.append(f"**Business impact:** {risk.get('business_impact', '—')}")
            lines.append(f"**Status:** {risk.get('status', '—')}")
            lines.append("")
    if r.actions_taken:
        lines.append("## Actions taken this month")
        for a in r.actions_taken:
            lines.append(f"- {a}")
        lines.append("")
    if r.actions_planned:
        lines.append("## Actions planned next month")
        for a in r.actions_planned:
            lines.append(f"- {a}")
        lines.append("")
    lines += ["## Bottom line", "", f"_{r.bottom_line}_"]
    return "\n".join(lines)


def _render_initial_assessment(r: InitialAssessmentReport) -> str:
    lines = ["# Initial Security Assessment — 30-Day Findings", "",
             r.executive_summary, ""]
    if r.findings:
        lines.append("## Top findings")
        for i, f in enumerate(r.findings[:10], 1):
            lines.append(f"### {i}. {f.get('title', '?')} _{f.get('severity', '?')}_")
            lines.append(f"**Business impact:** {f.get('business_impact', '—')}")
            lines.append(f"**Remediation effort:** {f.get('effort', '—')}")
            lines.append("")
    if r.compliance_gap_summary:
        lines += ["## Compliance posture", "", r.compliance_gap_summary, ""]
    if r.immediate_actions:
        lines.append("## Immediate actions (next 30 days)")
        for a in r.immediate_actions:
            lines.append(f"### {a.get('action', '?')}")
            lines.append(f"- Effort: {a.get('effort_estimate', '—')}")
            lines.append(f"- Why now: {a.get('why_now', '—')}")
            lines.append("")
    if r.unknown_areas:
        lines.append("## Still to investigate")
        for u in r.unknown_areas:
            lines.append(f"- {u}")
    return "\n".join(lines)


def _render_program_roadmap(r: ProgramRoadmapReport) -> str:
    lines = ["# Security Program Roadmap — 12 Months", ""]
    lines += ["## Where we started (Day 1)", "", r.where_we_started, ""]
    lines += ["## Where we are now", "", r.where_we_are_now, ""]
    if r.quarterly_milestones:
        lines.append("## Quarterly milestones")
        for q in r.quarterly_milestones:
            lines.append(f"### {q.get('quarter', '?')}: {q.get('milestone', '?')}")
            lines.append(f"- Risk reduction: {q.get('risk_reduction', '—')}")
            lines.append(f"- Investment: {q.get('investment', '—')}")
            lines.append("")
    if r.success_metrics:
        lines.append("## Success metrics")
        for m in r.success_metrics:
            lines.append(f"- {m}")
        lines.append("")
    lines += ["## Why this is worth it", "", r.investment_narrative]
    return "\n".join(lines)


def state_of_security() -> str:
    state = get_state()
    user_task = (
        "Generate a monthly State of Security brief for the executive audience. "
        "Use what you know about the org's risk register, decisions, and program health."
    )
    parsed, usage = _run("report_state_of_security", StateOfSecurityReport,
                         user_task=user_task)
    if parsed is None:
        raise RuntimeError("state_of_security generation returned no output")
    md = _render_state_of_security(parsed)
    return _finalize(kind="state_of_security", title="State of Security",
                     content_md_redacted=md, usage=usage)


def initial_assessment() -> str:
    from app.role import tenure_day
    tday = tenure_day()
    user_task = (
        f"Generate a 30-day Initial Assessment (current tenure day: {tday}). "
        "Frame every finding in business terms. Be honest about unknowns."
    )
    parsed, usage = _run("report_initial_assessment", InitialAssessmentReport,
                         user_task=user_task)
    if parsed is None:
        raise RuntimeError("initial_assessment generation returned no output")
    md = _render_initial_assessment(parsed)
    return _finalize(kind="initial_assessment", title="Initial Assessment",
                     content_md_redacted=md, usage=usage)


def program_roadmap() -> str:
    from app.role import tenure_day
    tday = tenure_day()
    user_task = (
        f"Generate a 12-month Security Program Roadmap (current tenure day: {tday}). "
        "Show trajectory from Day 1 to now to 12 months out."
    )
    parsed, usage = _run("report_program_roadmap", ProgramRoadmapReport,
                         user_task=user_task)
    if parsed is None:
        raise RuntimeError("program_roadmap generation returned no output")
    md = _render_program_roadmap(parsed)
    return _finalize(kind="program_roadmap", title="Security Program Roadmap",
                     content_md_redacted=md, usage=usage)


# ── Report registry: kind → generator function ──
#
# Used by:
# - `app/routers/reports.py::generate_report` (HTTP-triggered runs)
# - `app/claude/scheduler.py::_run_due_subscriptions` (recurring runs)
#
# Argument shape per kind:
# - `threat_landscape(service_id)` and `questions_for(team_or_person)` take a
#   single positional string; the scheduler reads this from `scope_json`.
# - Everything else takes no arguments and aggregates KB-wide context.
# Every generator returns the persisted `reports.id`.
REPORT_REGISTRY = {
    # Per-service deep dives. Reuse the same cached scope when run together.
    "threat_landscape":       threat_landscape,        # one service, STRIDE-style threats
    "cross_service_gaps":     cross_service_gaps,      # gaps across all services
    "oncall_handoff":         oncall_handoff,          # rotation-handoff brief
    # KB-wide aggregate views.
    "plan_30_60_90":          plan_30_60_90,           # 90-day partner plan
    "stakeholder_map":        stakeholder_map,         # who-owns-what
    "questions_for_team":     questions_for,           # interview prompts for a target
    "control_matrix":         control_matrix,          # controls vs. services
    "weekly_security_digest": weekly_security_digest,  # weekly aggregate
    # Coverage / visibility analyses.
    "attack_mapping":         attack_mapping,          # ATT&CK technique coverage
    "iam_audit":              iam_audit,               # IAM policy review
    "risk_register":          risk_register,           # full register as markdown
    # Leadership communication (Phase 7).
    "state_of_security":      state_of_security,
    "initial_assessment":     initial_assessment,
    "program_roadmap":        program_roadmap,
}


# ─── Batched subscription path ────────────────────────────────────────
#
# The scheduler's `_run_due_subscriptions` collects every due subscription
# whose kind is in `_BATCH_DISPATCH` and submits them as ONE Anthropic
# Message Batch (50% off both input + output rates). The handler below
# processes each result independently — same render + persistence shape
# as the sync `_finalize` flow.
#
# Excluded:
# - `attack_mapping` — has its own per-TM fan-out (see `app/claude/attack_mapping.py`).
# - `iam_audit`      — does not call Claude.
# Both fall through to the sync REPORT_REGISTRY path in the scheduler.


def _make_storage_scope(kind: str, sub_scope: dict, parsed) -> dict | None:
    """Mirror what the sync generators store in reports.scope_json."""
    if kind == "threat_landscape":
        return {"service_id": sub_scope.get("service_id")}
    if kind == "oncall_handoff":
        return {"service_id": sub_scope.get("service_id")}
    if kind == "questions_for_team":
        # Match sync questions_for(): store the redacted form.
        who = sub_scope.get("team_or_person") or ""
        return {"team_or_person": apply_redactions(who).redacted_text}
    return None


# A dispatch entry is the minimum each kind needs to (a) build a batch
# request from a sub's scope and (b) finalize a result. Static fields
# only; dynamic strings (titles built from parsed output, user-tasks
# built from app state) are computed via the lambdas at the bottom.
_BATCH_DISPATCH: dict[str, dict] = {
    "threat_landscape": {
        "output_format": ThreatLandscapeReport,
        "prompt_name":   "report_threat_landscape",
        "render_fn":     _render_threat,
        "needs_service_id": True,
        "make_user_task": lambda s: (
            "Produce a STRIDE-style threat landscape for the primary "
            "service. Use evidence chunk IDs you saw in scope."
        ),
        "make_title": lambda p, s: f"Threat landscape — {p.service_name}",
    },
    "cross_service_gaps": {
        "output_format": CrossServiceGapsReport,
        "prompt_name":   "report_cross_service_gaps",
        "render_fn":     _render_gaps,
        "needs_service_id": False,
        "make_user_task": lambda s: "Produce a cross-service gaps report.",
        "make_title":     lambda p, s: "Cross-service gaps & blind spots",
    },
    "plan_30_60_90": {
        "output_format": PlanReport,
        "prompt_name":   "report_30_60_90",
        "render_fn":     _render_plan,
        "needs_service_id": False,
        "make_user_task": lambda s: (
            "Produce a 30/60/90-day plan tailored to the user's scope."
        ),
        "make_title": lambda p, s: "30 / 60 / 90 day plan",
    },
    "stakeholder_map": {
        "output_format": StakeholderMap,
        "prompt_name":   "report_stakeholder_map",
        "render_fn":     _render_stakeholder,
        "needs_service_id": False,
        "make_user_task": lambda s: "Produce a stakeholder map.",
        "make_title":     lambda p, s: "Stakeholder map",
    },
    "questions_for_team": {
        "output_format": QuestionList,
        "prompt_name":   "report_questions_for_team",
        "render_fn":     _render_questions,
        "needs_service_id": False,
        "make_user_task": lambda s: (
            "Produce a ranked question list for interacting with: "
            f"{apply_redactions(s.get('team_or_person') or '').redacted_text}"
        ),
        "make_title": lambda p, s: (
            f"Questions for "
            f"{apply_redactions(s.get('team_or_person') or '').redacted_text}"
        ),
    },
    "control_matrix": {
        "output_format": ControlMatrix,
        "prompt_name":   "report_control_matrix",
        "render_fn":     _render_matrix,
        "needs_service_id": False,
        "make_user_task": lambda s: (
            "Produce a control coverage matrix across services in scope."
        ),
        "make_title": lambda p, s: "Control coverage matrix",
    },
    "weekly_security_digest": {
        "output_format": WeeklySecurityDigest,
        "prompt_name":   "report_weekly_security_digest",
        "render_fn":     _render_weekly_digest,
        "needs_service_id": False,
        "make_user_task": lambda s: (
            "Produce the weekly security digest summarizing this past "
            "week's activity."
        ),
        "make_title": lambda p, s: p.week_label or "Weekly security digest",
    },
    "oncall_handoff": {
        "output_format": OnCallHandoff,
        "prompt_name":   "report_oncall_handoff",
        "render_fn":     _render_oncall_handoff,
        "needs_service_id": True,
        "make_user_task": lambda s: (
            "Produce a per-service on-call handoff brief for the engineer "
            "about to take the pager."
        ),
        "make_title": lambda p, s: f"On-call handoff — {p.service_name}",
    },
    "risk_register": {
        "output_format": RiskRegisterReport,
        "prompt_name":   "report_risk_register",
        "render_fn":     _render_risk_register,
        "needs_service_id": False,
        # Pull the live risk list at submission time (matches sync flow).
        "make_user_task": lambda s: _build_risk_register_user_task(),
        "make_title":     lambda p, s: "Risk register",
    },
    "state_of_security": {
        "output_format": StateOfSecurityReport,
        "prompt_name":   "report_state_of_security",
        "render_fn":     _render_state_of_security,
        "needs_service_id": False,
        "make_user_task": lambda s: (
            "Generate a monthly State of Security brief for the executive "
            "audience. Use what you know about the org's risk register, "
            "decisions, and program health."
        ),
        "make_title": lambda p, s: "State of Security",
    },
    "initial_assessment": {
        "output_format": InitialAssessmentReport,
        "prompt_name":   "report_initial_assessment",
        "render_fn":     _render_initial_assessment,
        "needs_service_id": False,
        "make_user_task": lambda s: (
            _initial_assessment_user_task()
        ),
        "make_title": lambda p, s: "Initial Assessment",
    },
    "program_roadmap": {
        "output_format": ProgramRoadmapReport,
        "prompt_name":   "report_program_roadmap",
        "render_fn":     _render_program_roadmap,
        "needs_service_id": False,
        "make_user_task": lambda s: _program_roadmap_user_task(),
        "make_title": lambda p, s: "Security Program Roadmap",
    },
}


def _initial_assessment_user_task() -> str:
    from app.role import tenure_day
    tday = tenure_day()
    return (
        f"Generate a 30-day Initial Assessment (current tenure day: {tday}). "
        "Frame every finding in business terms. Be honest about unknowns."
    )


def _program_roadmap_user_task() -> str:
    from app.role import tenure_day
    tday = tenure_day()
    return (
        f"Generate a 12-month Security Program Roadmap (current tenure "
        f"day: {tday}). Show trajectory from Day 1 to now to 12 months out."
    )


def _build_sub_batch_request(sub: dict) -> dict | None:
    """Turn one due subscription into one batch request dict.

    Returns None for kinds not in `_BATCH_DISPATCH` (caller should
    fall back to the sync REPORT_REGISTRY path) or for scope-bearing
    kinds missing their required scope field.
    """
    from app.claude.batch_helpers import tool_params_for
    kind = sub["kind"]
    spec = _BATCH_DISPATCH.get(kind)
    if spec is None:
        return None
    try:
        scope = json.loads(sub.get("scope_json") or "{}")
    except json.JSONDecodeError:
        scope = {}

    service_id = None
    if spec["needs_service_id"]:
        service_id = scope.get("service_id")
        if not service_id:
            return None  # required scope missing, skip
    if kind == "questions_for_team" and not scope.get("team_or_person"):
        return None

    tools, tool_choice = tool_params_for(spec["output_format"])
    user_task = spec["make_user_task"](scope)
    return {
        "custom_id": sub["id"],
        "params": {
            "model": MODEL,
            "max_tokens": 8192,
            "system": [{
                "type": "text",
                "text": load_prompt(spec["prompt_name"]),
                "cache_control": CACHE_1H,
            }],
            "messages": [{
                "role": "user",
                "content": [
                    build_scope_block(service_id=service_id),
                    {"type": "text", "text": user_task},
                ],
            }],
            "tools": tools,
            "tool_choice": tool_choice,
        },
    }


def schedule_batch_for_subs(subs: list[dict]) -> tuple[str | None, list[dict]]:
    """Submit one batch covering every batch-eligible subscription.

    Returns `(batch_row_id, leftover_subs)` — leftover_subs are subs the
    scheduler should fall back to the sync REPORT_REGISTRY path for
    (currently: `attack_mapping`, `iam_audit`, or any sub missing required
    scope fields). The caller (`_run_due_subscriptions`) is responsible
    for that fallback.
    """
    from app.claude import batches as batches_mod
    requests = []
    by_sub_id: dict[str, dict] = {}
    leftover: list[dict] = []
    for sub in subs:
        req = _build_sub_batch_request(sub)
        if req is None:
            leftover.append(sub)
            continue
        requests.append(req)
        try:
            scope = json.loads(sub.get("scope_json") or "{}")
        except json.JSONDecodeError:
            scope = {}
        by_sub_id[sub["id"]] = {
            "kind": sub["kind"],
            "scope": scope,
            "role_mode": sub.get("role_mode"),
        }
    if not requests:
        return None, leftover
    batch_id = batches_mod.submit(
        kind="report_subscription",
        requests=requests,
        payload={"by_sub_id": by_sub_id},
    )
    return batch_id, leftover


def _handle_report_subscription(custom_id: str, msg, payload: dict) -> None:
    """Per-result handler for batched report subscriptions."""
    from app.claude.batch_helpers import extract_validated
    from app.storage import subscriptions_store

    info = (payload.get("by_sub_id") or {}).get(custom_id)
    if info is None:
        log.warning("report_subscription %s: no payload entry; skipping",
                    custom_id)
        return
    kind = info["kind"]
    spec = _BATCH_DISPATCH.get(kind)
    if spec is None:
        log.warning("report_subscription %s: kind=%s not in dispatch",
                    custom_id, kind)
        return
    parsed = extract_validated(msg, spec["output_format"])
    if parsed is None:
        log.warning("report_subscription %s kind=%s: no structured output",
                    custom_id, kind)
        return

    md_redacted = spec["render_fn"](parsed)
    mapping = load_rehydration_map(_ph_in(md_redacted))
    md = rehydrate(md_redacted, mapping)

    usage = getattr(msg, "usage", None)
    state = get_state()
    role_mode = info.get("role_mode") or state.role_mode.value

    report_id = reports_store.insert(
        kind=kind,
        title=spec["make_title"](parsed, info.get("scope") or {}),
        content_md=md,
        content_md_redacted=md_redacted,
        role_mode=role_mode,
        model=getattr(msg, "model", MODEL),
        scope=_make_storage_scope(kind, info.get("scope") or {}, parsed),
        tokens_in=getattr(usage, "input_tokens", None) if usage else None,
        tokens_out=getattr(usage, "output_tokens", None) if usage else None,
        cache_read_in=getattr(usage, "cache_read_input_tokens", None) if usage else None,
        cache_create_in=getattr(usage, "cache_creation_input_tokens", None) if usage else None,
    )
    subscriptions_store.mark_run(custom_id, report_id)
    publish("reports.global", "subscription_run",
            {"subscription_id": custom_id, "report_id": report_id,
             "kind": kind})


# Register handler at import time. Done at module scope (not inside a
# function) so the registration happens whenever reports.py is imported,
# which the scheduler does eagerly.
def _register_batch_handler() -> None:
    from app.claude import batches as batches_mod
    batches_mod.register("report_subscription")(_handle_report_subscription)


_register_batch_handler()
