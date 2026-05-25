"""Postmortem authoring scaffold.

A user freewrites what happened. Sonnet drafts the structured fields
(summary, timeline, what_failed, why, contributing factors, mitigations,
action items). On save, action items become followups; services
affected get linked.
"""
from __future__ import annotations

import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.kb.entities import find_by_name
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.schemas import PostmortemDraftPayload, PostmortemFields
from app.storage import followups_store, postmortems_store

log = logging.getLogger("tank.postmortem")


def draft_from_freewrite(*, title: str, freewrite: str,
                         severity: str | None = None) -> str:
    """Create a draft postmortem from user freewrite. Returns pm_id."""
    redacted = apply_redactions(freewrite).redacted_text
    payload = _generate_draft(title, redacted, severity)

    if payload:
        fields = payload.fields.model_dump()
        title = payload.title
        services = payload.services_affected
        severity = severity or payload.severity_guess
    else:
        fields = {"summary": "", "timeline": [], "what_failed": "",
                  "why": "", "contributing_factors": [],
                  "mitigations": [], "action_items": []}
        services = []

    body_md_red = _render(title, fields)
    body_md = rehydrate(body_md_red, load_rehydration_map())

    # resolve service names to entity IDs
    svc_ids: list[str] = []
    for s in services:
        card = find_by_name("Service", s)
        if card:
            svc_ids.append(card["id"])

    pm_id = postmortems_store.create(
        title=title, fields=fields,
        body_md=body_md, body_md_redacted=body_md_red,
        severity=severity, services_affected=svc_ids,
    )
    return pm_id


def publish(pm_id: str) -> dict:
    """Mark published; create followups for each action item; return summary."""
    pm = postmortems_store.get(pm_id)
    if not pm:
        raise ValueError(f"postmortem not found: {pm_id}")
    if pm["status"] == "published":
        return {"already_published": True}
    fields = pm.get("fields") or {}
    fu_ids: list[str] = []
    for action in fields.get("action_items", []):
        fid = followups_store.create(
            title=str(action)[:200],
            body=str(action),
            source_kind="postmortem",
            source_id=pm_id,
        )
        fu_ids.append(fid)
    postmortems_store.set_status(pm_id, "published")

    # Extract lessons from the published postmortem (Phase 15).
    lesson_ids: list[str] = []
    try:
        from app.claude import lesson_extractor
        lesson_ids = lesson_extractor.extract_from_postmortem(
            pm_id, pm.get("body_md_redacted") or pm.get("body_md") or "",
        )
    except Exception as exc:
        log.warning("lesson extraction on publish failed: %s", exc)

    return {"postmortem_id": pm_id, "followup_ids": fu_ids,
            "lesson_ids": lesson_ids,
            "services_affected": pm.get("services_affected") or []}


def _generate_draft(title: str, redacted_freewrite: str,
                    severity: str | None) -> PostmortemDraftPayload | None:
    client = get_client()
    try:
        prompt = load_prompt("postmortem_draft")
    except FileNotFoundError:
        log.warning("postmortem_draft prompt missing")
        return None
    try:
        sev_hint = f"User-stated severity: {severity}" if severity else ""
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": [
                           {"type": "text", "text": f"# {title}"},
                           {"type": "text", "text": redacted_freewrite},
                           {"type": "text",
                            "text": f"{sev_hint}\n\nDraft the structured "
                                    "postmortem from this freewrite."},
                       ]}],
            output_format=PostmortemDraftPayload,
        )
        log_token_usage("postmortem.draft", MODEL, getattr(resp, "usage", None))
        return getattr(resp, "parsed_output", None)
    except Exception as exc:
        log.warning("postmortem draft LLM failed: %s", exc)
        return None


def _render(title: str, fields: dict) -> str:
    lines = [f"# {title}", "", "## Summary", fields.get("summary", "—"), ""]
    timeline = fields.get("timeline") or []
    if timeline:
        lines.append("## Timeline")
        for t in timeline:
            lines.append(f"- {t}")
        lines.append("")
    lines.extend(["## What failed", fields.get("what_failed", "—"), ""])
    lines.extend(["## Why", fields.get("why", "—"), ""])
    cf = fields.get("contributing_factors") or []
    if cf:
        lines.append("## Contributing factors")
        for x in cf:
            lines.append(f"- {x}")
        lines.append("")
    mit = fields.get("mitigations") or []
    if mit:
        lines.append("## Mitigations applied")
        for x in mit:
            lines.append(f"- {x}")
        lines.append("")
    ai = fields.get("action_items") or []
    if ai:
        lines.append("## Action items")
        for x in ai:
            lines.append(f"- [ ] {x}")
        lines.append("")
    return "\n".join(lines)
