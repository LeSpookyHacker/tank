"""Prioritization Engine — generates top-5 quarterly action plan from risk context."""
from __future__ import annotations

import json
import logging
import re
import time

from app.claude.reports import _build_scope_block
from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.role import get_state
from app.storage import reports_store

log = logging.getLogger("tank.prioritization")

_KIND = "prioritization"


def generate() -> str:
    """Generate a quarterly prioritization. Returns report_id."""
    from app.db import LOCK, get_conn
    conn = get_conn()

    # Pull risk register context
    with LOCK:
        risks = conn.execute(
            "SELECT title, category, inherent_likelihood, inherent_impact, "
            "residual_likelihood, residual_impact, treatment, status "
            "FROM risks WHERE status = 'open' LIMIT 50"
        ).fetchall()
        open_vulns = conn.execute(
            "SELECT cve_id, title, severity, cvss_score FROM vulnerabilities "
            "WHERE triage_status = 'new' OR status = 'open' LIMIT 20"
        ).fetchall()

    state = get_state()
    risk_text = "\n".join(
        f"- [{r['category']}] {r['title']} | "
        f"inherent L{r['inherent_likelihood']}×I{r['inherent_impact']} | "
        f"residual L{r['residual_likelihood']}×I{r['residual_impact']} | "
        f"{r['treatment']}"
        for r in risks
    ) or "(no risk register entries yet)"

    vuln_text = "\n".join(
        f"- [{v['severity']}] {v['cve_id'] or ''} {v['title']} "
        f"(CVSS {v['cvss_score'] or '?'})"
        for v in open_vulns
    ) or "(no open vulnerabilities)"

    from app.storage import asset_inventory_store as inv
    stack = inv.get_all()
    gaps = [f"- {s['capability_category']}: none/partial" for s in stack
            if s.get("deployment_status") in ("none", None)]
    stack_text = "\n".join(gaps) or "(stack audit not completed)"

    user_content = f"""
Risk register ({len(risks)} items):
{risk_text}

Open vulnerabilities ({len(open_vulns)} items):
{vuln_text}

Security stack gaps (no/partial coverage):
{stack_text}

Compliance targets: {', '.join(state.compliance_targets) or 'none specified'}

Generate the top-5 quarterly priorities. Be concrete and opinionated.
"""

    scope_block = _build_scope_block()
    client = get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": load_prompt("prioritization"),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [scope_block, {"type": "text", "text": user_content}],
        }],
    )
    usage = getattr(resp, "usage", None)
    log_token_usage("prioritization", MODEL, usage)

    raw = "".join(getattr(b, "text", "") for b in (resp.content or []))

    json_match = re.search(r'\{.*"priorities".*\}', raw, re.DOTALL)
    if not json_match:
        raise RuntimeError("prioritization returned no JSON")

    try:
        data = json.loads(json_match.group(0))
        priorities = data.get("priorities", [])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"prioritization JSON parse error: {e}") from e

    md = _render(priorities)

    from app.redact.engine import rehydrate
    from app.redact.store import load_rehydration_map
    mapping = load_rehydration_map()
    content_md = rehydrate(md, mapping)

    from app.role import get_state as _gs
    st = _gs()
    report_id = reports_store.insert(
        kind=_KIND,
        title="Security Priorities — This Quarter",
        content_md=content_md,
        content_md_redacted=md,
        role_mode=st.role_mode.value,
        model=MODEL,
        scope=None,
        tokens_in=getattr(usage, "input_tokens", 0) if usage else None,
        tokens_out=getattr(usage, "output_tokens", 0) if usage else None,
        cache_read_in=getattr(usage, "cache_read_input_tokens", 0) if usage else None,
        cache_create_in=getattr(usage, "cache_creation_input_tokens", 0) if usage else None,
    )
    log.info("prioritization generated: id=%s, %d items", report_id, len(priorities))
    return report_id


def _render(priorities: list[dict]) -> str:
    lines = ["# Security Priorities — This Quarter", ""]
    for p in priorities:
        rank = p.get("rank", "?")
        lines.append(f"## {rank}. {p.get('title', '?')}")
        if p.get("scope"):
            lines.append(f"_Scope: {p['scope']}_")
        lines.append("")
        lines.append(p.get("rationale", ""))
        lines.append("")
        lines.append(f"**Done when:** {p.get('done_condition', '—')}")
        lines.append(f"**Effort:** {p.get('effort', '—')} · **Owner:** {p.get('owner', '—')}")
        lines.append("")
    return "\n".join(lines)
