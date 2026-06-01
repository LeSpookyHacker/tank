"""Anniversary retrospective generator.

Fires at Day 30/60/90/180/365 (scheduler-driven). Produces a
retrospective report that walks the entity-graph + chat-history
windows ending on the anniversary and surfaces what changed.
"""
from __future__ import annotations

import logging

from app.claude import batches
from app.claude.batch_helpers import extract_validated, tool_params_for
from app.claude.caching import build_scope_block
from app.claude.event_bus import publish
from app.claude.reports import _build_scope_block, _finalize
from app.config import MODEL, get_client, load_prompt
from app.redact.engine import rehydrate
from app.redact.store import load_rehydration_map
from app.role import get_state, tenure_day
from app.schemas import AnniversaryRetro
from app.storage import reports_store

log = logging.getLogger("tank.anniversary")


def generate(day_n: int) -> str:
    """Generate the Day-`day_n` retrospective."""
    state = get_state()
    scope = state.user_scope.model_dump() if state.user_scope else {}
    user_task = (
        f"User's scope: {scope}\n"
        f"Days into tenure: {day_n}\n\n"
        "Produce a retrospective: what was built, what was learned, "
        "what's drifted since onboarding, what to prioritize over the "
        f"next 30 days."
    )
    client = get_client()
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": load_prompt("anniversary"),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    _build_scope_block(),
                    {"type": "text", "text": user_task},
                ],
            }],
            output_format=AnniversaryRetro,
        )
        parsed = getattr(resp, "parsed_output", None)
        usage = getattr(resp, "usage", None)
    except Exception as exc:
        log.exception("anniversary retro day %d failed", day_n)
        raise

    if parsed is None:
        raise RuntimeError("anniversary retro returned no structured output")

    md = _render_retro(parsed)
    usage_d = {}
    if usage:
        usage_d = {
            "tokens_in": getattr(usage, "input_tokens", 0) or 0,
            "tokens_out": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_in": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_create_in": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        }
    return _finalize(
        kind=f"anniversary_{day_n}",
        title=f"Day-{day_n} retrospective",
        content_md_redacted=md,
        usage=usage_d,
        scope={"day_n": day_n},
    )


def _render_retro(r: AnniversaryRetro) -> str:
    lines = [f"# Day-{r.day_n} retrospective", "", r.summary, ""]

    if r.what_you_built:
        lines.append("## What you built")
        for x in r.what_you_built:
            lines.append(f"- {x}")
        lines.append("")

    if r.what_you_learned:
        lines.append("## What you learned")
        for x in r.what_you_learned:
            lines.append(f"- {x}")
        lines.append("")

    if r.what_drifted:
        lines.append("## What drifted")
        for x in r.what_drifted:
            lines.append(f"- {x}")
        lines.append("")

    if r.next_30_days:
        lines.append("## Next 30 days")
        for x in r.next_30_days:
            lines.append(f"- {x}")
        lines.append("")

    return "\n".join(lines)


# ─── Batch path (anniversary_bundle) ──────────────────────────────────

def _user_task_for(day_n: int) -> str:
    state = get_state()
    scope = state.user_scope.model_dump() if state.user_scope else {}
    return (
        f"User's scope: {scope}\n"
        f"Days into tenure: {day_n}\n\n"
        "Produce a retrospective: what was built, what was learned, "
        "what's drifted since onboarding, what to prioritize over the "
        "next 30 days."
    )


def build_batch_request(day_n: int) -> dict:
    """Build the generic-retro batch request (custom_id `generic-{N}`)."""
    tools, tool_choice = tool_params_for(AnniversaryRetro)
    return {
        "custom_id": f"generic-{day_n}",
        "params": {
            "model": MODEL,
            "max_tokens": 4096,
            "system": [{
                "type": "text",
                "text": load_prompt("anniversary"),
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": [{
                "role": "user",
                "content": [
                    build_scope_block(),
                    {"type": "text", "text": _user_task_for(day_n)},
                ],
            }],
            "tools": tools,
            "tool_choice": tool_choice,
        },
    }


def schedule_batch(day_n: int) -> str | None:
    """Submit the milestone bundle: generic + security + (philosophy).

    All three artifacts ride in one batch — they fire at the same tenure
    milestone, share no per-result dependency, and bundling means one
    API submit/poll cycle for the whole milestone.
    """
    from app.claude import anniversary_security, philosophy
    requests = [
        build_batch_request(day_n),
        anniversary_security.build_batch_request(day_n),
    ]
    phil_mode = "seed" if day_n == 30 else (
        "evolve" if day_n in (60, 90, 180, 365) else None
    )
    if phil_mode is not None:
        phil_req = philosophy.build_batch_request(day_n, phil_mode)
        if phil_req is not None:
            requests.append(phil_req)
    return batches.submit(
        kind="anniversary_bundle",
        requests=requests,
        payload={"day_n": day_n},
    )


@batches.register("anniversary_bundle")
def _handle_anniversary_bundle(custom_id: str, msg, payload: dict) -> None:
    """Dispatch by custom_id prefix to the right persistence path."""
    day_n = int(payload.get("day_n", 0))
    state = get_state()
    usage = getattr(msg, "usage", None)
    model_used = getattr(msg, "model", MODEL)

    def _usage_kwargs() -> dict:
        if not usage:
            return {"tokens_in": None, "tokens_out": None,
                    "cache_read_in": None, "cache_create_in": None}
        return {
            "tokens_in": getattr(usage, "input_tokens", None),
            "tokens_out": getattr(usage, "output_tokens", None),
            "cache_read_in": getattr(usage, "cache_read_input_tokens", None),
            "cache_create_in": getattr(usage, "cache_creation_input_tokens", None),
        }

    if custom_id.startswith("generic-"):
        parsed = extract_validated(msg, AnniversaryRetro)
        if parsed is None:
            return
        md_red = _render_retro(parsed)
        md = rehydrate(md_red, load_rehydration_map())
        rid = reports_store.insert(
            kind=f"anniversary_{day_n}",
            title=f"Day-{day_n} retrospective",
            content_md=md, content_md_redacted=md_red,
            role_mode=state.role_mode.value,
            model=model_used,
            scope={"day_n": day_n},
            **_usage_kwargs(),
        )
        publish("scheduler.global", "anniversary_fired",
                {"day_n": day_n, "report_id": rid})
        return

    if custom_id.startswith("security-"):
        from app.claude.anniversary_security import (
            _render as _render_security,
        )
        parsed = extract_validated(msg, AnniversaryRetro)
        if parsed is None:
            return
        md = _render_security(parsed)
        rid = reports_store.insert(
            kind=f"anniversary_security_{day_n}",
            title=f"Day-{day_n} security retro",
            content_md=md, content_md_redacted=md,
            role_mode=state.role_mode.value,
            model=model_used,
            scope={"day_n": day_n},
            **_usage_kwargs(),
        )
        publish("scheduler.global", "anniversary_security_fired",
                {"day_n": day_n, "report_id": rid})
        return

    if custom_id.startswith("philosophy-"):
        from app.claude import philosophy
        from app.schemas import PhilosophyDoc
        parsed = extract_validated(msg, PhilosophyDoc)
        if parsed is None:
            return
        # custom_id format: philosophy-{day}-{mode}
        try:
            mode = custom_id.split("-")[-1]
        except Exception:
            mode = "evolve"
        rid = philosophy.persist_from_batch(
            parsed, day_n=day_n, mode=mode, msg=msg,
        )
        evt = "philosophy_seeded" if mode == "seed" else "philosophy_evolved"
        publish("scheduler.global", evt,
                {"report_id": rid, "day_n": day_n})
        return

    log.warning("anniversary_bundle: unknown custom_id %r", custom_id)
