"""Security program health dashboard.

GET /security-program  — HTML dashboard with aggregated metrics
GET /api/security-program/metrics — JSON metrics snapshot
POST /api/security-program/executive-brief — Claude-generated exec brief
POST /api/security-program/snapshot — manually trigger a metrics snapshot
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import MODEL, TEMPLATES_DIR, get_client, load_prompt, log_token_usage
from app.db import LOCK, get_conn
from app.rate_limiter import limiter
from app.redact.engine import apply_redactions
from app.schemas import ExecutiveBriefOutput, SecurityProgramMetrics

log = logging.getLogger("tank.routers.security_program")

router = APIRouter()
api = APIRouter(prefix="/api/security-program")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Metrics collection ──────────────────────────────────────────────

def _collect_metrics() -> SecurityProgramMetrics:
    conn = get_conn()
    now = time.time()
    thirty_days_ago = now - 30 * 86400
    ninety_days_ago = now - 90 * 86400

    def _scalar(sql: str, *params) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0

    # Threat models.
    tm_total = _scalar("SELECT COUNT(DISTINCT service_entity_id) FROM threat_models")
    # Drifted: latest TM per service where arch_snapshot_hash differs from
    # the hash computed over current chunks (approximated as: TM exists but
    # the service has chunks with a higher updated timestamp than TM).
    # Simplified heuristic: count services whose latest TM is older than 60d.
    sixty_days_ago = now - 60 * 86400
    tm_drifted = _scalar(
        "SELECT COUNT(DISTINCT service_entity_id) FROM threat_models "
        "WHERE generated_at < ?", sixty_days_ago,
    )
    tm_updated_30d = _scalar(
        "SELECT COUNT(*) FROM threat_models WHERE generated_at >= ?",
        thirty_days_ago,
    )

    # Vulnerabilities.
    vuln_counts: dict = {}
    for sev in ("critical", "high", "medium", "low"):
        n = _scalar(
            "SELECT COUNT(*) FROM vulnerabilities WHERE status='open' AND severity=?",
            sev,
        )
        vuln_counts[sev] = n

    avg_age_row = conn.execute(
        "SELECT AVG((? - created_at) / 86400.0) FROM vulnerabilities WHERE status='open'",
        (now,),
    ).fetchone()
    vuln_avg_age = round(float(avg_age_row[0] or 0), 1)

    # Risk register.
    risks_open = _scalar("SELECT COUNT(*) FROM risks WHERE status='open'")
    risks_overdue = _scalar(
        "SELECT COUNT(*) FROM risks WHERE status='open' AND review_at IS NOT NULL AND review_at <= ?",
        int(now),
    )

    # Decisions.
    dec_accepted_open = _scalar(
        "SELECT COUNT(*) FROM decisions WHERE kind='accepted_risk' AND status='open'"
    )
    dec_expiring_30d = _scalar(
        "SELECT COUNT(*) FROM decisions WHERE status='open' AND expires_at IS NOT NULL "
        "AND expires_at BETWEEN ? AND ?",
        now, now + 30 * 86400,
    )

    # Compliance.
    comp_total = _scalar("SELECT COUNT(*) FROM entities WHERE type='Control'")
    comp_with_evidence = _scalar(
        "SELECT COUNT(DISTINCT control_id) FROM compliance_evidence"
    )

    # Postmortems.
    pm_published_90d = _scalar(
        "SELECT COUNT(*) FROM postmortems_drafts WHERE status='published' AND updated_at >= ?",
        ninety_days_ago,
    )

    # Followups.
    fu_open = _scalar("SELECT COUNT(*) FROM followups WHERE status='open'")
    fu_done_90d = _scalar(
        "SELECT COUNT(*) FROM followups WHERE status='done' AND updated_at >= ?",
        ninety_days_ago,
    )

    # Design reviews.
    dr_open = _scalar(
        "SELECT COUNT(*) FROM design_reviews WHERE status NOT IN ('approved','rejected','withdrawn')"
    )
    dr_approved_90d = _scalar(
        "SELECT COUNT(*) FROM design_reviews WHERE status='approved' AND updated_at >= ?",
        ninety_days_ago,
    )

    return SecurityProgramMetrics(
        threat_models_total=tm_total,
        threat_models_drifted=tm_drifted,
        threat_models_updated_30d=tm_updated_30d,
        vulns_open_critical=vuln_counts.get("critical", 0),
        vulns_open_high=vuln_counts.get("high", 0),
        vulns_open_medium=vuln_counts.get("medium", 0),
        vulns_open_low=vuln_counts.get("low", 0),
        vulns_avg_age_days=vuln_avg_age,
        risks_open=risks_open,
        risks_review_overdue=risks_overdue,
        decisions_accepted_risk_open=dec_accepted_open,
        decisions_expiring_30d=dec_expiring_30d,
        compliance_controls_total=comp_total,
        compliance_controls_with_evidence=comp_with_evidence,
        postmortems_published_90d=pm_published_90d,
        followups_open=fu_open,
        followups_done_90d=fu_done_90d,
        design_reviews_open=dr_open,
        design_reviews_approved_90d=dr_approved_90d,
        snapshot_at=now,
    )


def take_snapshot() -> str:
    """Persist a metrics snapshot. Called by the scheduler on Sunday 09:30."""
    import uuid
    metrics = _collect_metrics()
    sid = uuid.uuid4().hex
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO security_program_snapshots (id, snapshot_at, metrics_json) "
            "VALUES (?, ?, ?)",
            (sid, int(metrics.snapshot_at), json.dumps(metrics.model_dump())),
        )
    return sid


def _history(limit: int = 12) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM security_program_snapshots ORDER BY snapshot_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    result = []
    for r in rows:
        try:
            m = json.loads(r["metrics_json"])
        except Exception:
            m = {}
        result.append({"id": r["id"], "snapshot_at": r["snapshot_at"], **m})
    return result


# ── API endpoints ───────────────────────────────────────────────────

@api.get("/metrics")
async def metrics_json() -> dict:
    m = _collect_metrics()
    return m.model_dump()


@api.post("/snapshot")
async def manual_snapshot() -> dict:
    sid = take_snapshot()
    return {"snapshot_id": sid}


@api.post("/executive-brief")
@limiter.limit("5/hour")
async def executive_brief(request: Request) -> dict:
    """Generate an executive-level security brief via Claude."""
    metrics = _collect_metrics()
    metrics_text = json.dumps(metrics.model_dump(), indent=2)

    try:
        prompt = load_prompt("executive_security_brief")
    except FileNotFoundError:
        prompt = "Produce a concise executive security brief from the metrics below."

    client = get_client()
    system_block = {
        "type": "text", "text": prompt,
        "cache_control": {"type": "ephemeral"},
    }
    task_text = (
        "Security program metrics snapshot:\n"
        f"```json\n{metrics_text}\n```\n\n"
        "Produce the executive security brief."
    )

    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[system_block],
            messages=[{"role": "user", "content": [
                {"type": "text",
                 "text": apply_redactions(task_text).redacted_text},
            ]}],
            output_format=ExecutiveBriefOutput,
        )
        log_token_usage("security_program.executive_brief", MODEL,
                        getattr(resp, "usage", None))
        result: ExecutiveBriefOutput = resp.parsed_output
        return result.model_dump()
    except Exception:
        log.warning("executive brief generation failed", exc_info=True)
        return {"error": "Brief generation failed — check server logs."}


# ── HTML page ───────────────────────────────────────────────────────

@router.get("/security-program", response_class=HTMLResponse)
async def page_security_program(request: Request) -> HTMLResponse:
    metrics = _collect_metrics()
    history = _history(limit=12)

    compliance_pct = 0
    if metrics.compliance_controls_total > 0:
        compliance_pct = round(
            100 * metrics.compliance_controls_with_evidence / metrics.compliance_controls_total
        )

    followup_done_pct = 0
    total_fu = metrics.followups_open + metrics.followups_done_90d
    if total_fu > 0:
        followup_done_pct = round(100 * metrics.followups_done_90d / total_fu)

    return templates.TemplateResponse(
        request=request,
        name="security_program.html",
        context={
            "metrics": metrics,
            "history": history,
            "compliance_pct": compliance_pct,
            "followup_done_pct": followup_done_pct,
        },
    )


@api.post("/priorities/generate")
async def generate_priorities(background_tasks: BackgroundTasks) -> dict:
    """Generate quarterly security prioritization via the Prioritization Engine."""
    background_tasks.add_task(_generate_priorities_bg)
    return {"ok": True, "message": "Prioritization generating. Check Reports in ~30s."}


@api.get("/priorities")
async def get_priorities() -> dict:
    """Return the latest prioritization report if one exists."""
    from app.storage import reports_store
    rows = reports_store.list_by_kind("prioritization", limit=1)
    if not rows:
        return {"priorities": None}
    return {"priorities": rows[0]}


def _generate_priorities_bg() -> None:
    import logging as _log
    log = _log.getLogger("tank.security_program")
    try:
        from app.claude.prioritization import generate
        generate()
    except Exception:
        log.exception("prioritization generation failed")


router.include_router(api)
