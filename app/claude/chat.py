"""Streaming chat with tool use over the KB.

Pioneers two patterns in this codebase: SSE streaming and
Anthropic tool use. The shape is:

    1. Redact the user message → pre-redacted text + map delta.
    2. Embed the redacted query locally → vector search.
    3. Hybrid retrieve top chunks; pull entity cards for top entities
       cited in those chunks.
    4. Build messages = [cached_system, cached_kb, history..., user].
    5. Call `client.messages.stream(...)` with `tools=KB_TOOLS`.
    6. Stream-loop:
       - text deltas → publish chat.text_delta events
       - tool_use → execute locally, append tool_result, continue
       - end_turn → finalize: rehydrate, persist redacted_view +
         display_view + citations, publish done event with token stats.

The loop runs inside an asyncio.Task; the router endpoint streams its
events to the browser via SSE.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.claude.caching import build_kb_block, build_system_block
from app.claude.event_bus import publish
from app.config import MODEL, get_client
from app.kb.entities import get_card
from app.kb.search import hybrid_search
from app.kb.tools import TOOL_SCHEMAS, execute_tool
from app.redact.engine import apply_redactions, rehydrate
from app.redact.store import load_rehydration_map
from app.storage import (conversations_store, entities_store,
                         messages_store)

log = logging.getLogger("tank.chat")


# ---------------- helpers ----------------


def _build_placeholder_re() -> re.Pattern:
    """Build the placeholder regex from all registered redaction rules so
    new categories are automatically recognized without manual updates here."""
    try:
        from app.redact.rules import ALL_RULES
        from app.redact.secrets import ALL_RULES as SECRET_RULES
        all_rules = list(ALL_RULES) + [r for r in SECRET_RULES if r not in ALL_RULES]
    except Exception:
        all_rules = []
    prefixes: list[str] = []
    for rule in all_rules:
        fmt = getattr(rule, "placeholder_fmt", "")
        # fmt looks like "[PREFIX_{n:03d}]" — extract PREFIX
        m = re.match(r"\[([A-Z0-9_]+)_\{", fmt)
        if m:
            prefixes.append(re.escape(m.group(1)))
    if not prefixes:
        # Fallback to hardcoded list if import fails
        prefixes = [
            "EMAIL", "INTERNAL_HOST", "HOST", "PRIVATE_IP", "PUBLIC_IP",
            "AWS_ACCT", "AWS_ARN", "GCP_PROJECT", "AZURE_SUB", "SECRET", "PERSON",
        ]
    alt = "|".join(prefixes)
    return re.compile(r"\[(?:" + alt + r"|CUSTOM[A-Z_]*)_\d+\]")


_PLACEHOLDER_RE = _build_placeholder_re()


def _used_placeholders(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        if not t:
            continue
        out.update(_PLACEHOLDER_RE.findall(t))
    return out


def _entity_cards_for_hits(hits: list, k: int = 8) -> list[dict]:
    """Pull entity cards for the top-K entities cited across hits."""
    if not hits:
        return []
    chunk_ids = [h.chunk_id for h in hits]
    placeholders = ",".join("?" * len(chunk_ids))
    rows = entities_store.get_conn().execute(
        f"SELECT entity_id, COUNT(*) AS n "
        f"FROM entity_chunks "
        f"WHERE chunk_id IN ({placeholders}) "
        f"GROUP BY entity_id ORDER BY n DESC LIMIT ?",
        (*chunk_ids, k),
    ).fetchall()
    cards = []
    for r in rows:
        c = get_card(r["entity_id"])
        if c:
            cards.append(c)
    return cards


def _history_for_claude(conv_id: str) -> list[dict]:
    """Reconstruct the existing message list in Claude's content-block
    format. We replay `content_json` for assistant turns to preserve
    tool_use / tool_result blocks; user turns are plain text.
    """
    out: list[dict] = []
    for m in messages_store.list_for_conv(conv_id):
        if m["role"] == "user":
            text = m.get("redacted_view") or m.get("content_json") or ""
            try:
                # content_json may be a JSON string for legacy rows.
                if text.startswith("["):
                    out.append({"role": "user", "content": json.loads(text)})
                    continue
            except Exception:
                pass
            out.append({"role": "user", "content": text})
        elif m["role"] == "assistant":
            try:
                blocks = json.loads(m["content_json"])
                out.append({"role": "assistant", "content": blocks})
            except Exception:
                out.append({"role": "assistant",
                            "content": m.get("redacted_view") or ""})
    return out


# ---------------- the loop ----------------

@dataclass
class TurnEvent:
    kind: str           # 'text_delta'|'tool_use'|'tool_result'|'done'|'error'
    payload: Any


async def run_turn(conversation_id: str, user_text: str) -> str:
    """Run one assistant turn. Returns the message_id of the persisted
    assistant message. Publishes events to chat.<conv> via the event bus.

    Caller is expected to have already persisted the user message; this
    function just consumes the conversation state.
    """
    conv = conversations_store.get(conversation_id)
    if not conv:
        raise ValueError(f"no conversation {conversation_id}")

    topic = f"chat.{conversation_id}"

    # 1. Redact the user text. Defense in depth — chunks were already
    #    redacted at ingest, but user input is fresh.
    redacted = apply_redactions(user_text)
    user_redacted = redacted.redacted_text

    # 2. Retrieve.
    hits = hybrid_search(user_redacted, k=12)
    hit_dicts = [
        {
            "chunk_id": h.chunk_id,
            "document_id": h.document_id,
            "section_path": h.section_path,
            "snippet": h.snippet,
            "score": h.score,
            "source": h.source,
        }
        for h in hits
    ]
    entity_cards = _entity_cards_for_hits(hits)

    # 3. Build prompt.
    role_mode = conv["role_mode"]
    try:
        from app.role import current_lens
        lens = current_lens()
    except Exception:
        lens = None

    # Phase 6: inject project notes only for project-scoped conversations.
    # Global / side-panel conversations have no project_id, so notes = "".
    project_notes = ""
    proj_id = conv.get("project_id")
    if proj_id:
        try:
            from app.storage.projects_store import get_project as _get_project
            proj = _get_project(proj_id)
            if proj:
                raw_notes = proj.get("notes") or ""
                project_notes = apply_redactions(raw_notes).redacted_text if raw_notes else ""
        except Exception:
            pass

    system_blocks = [build_system_block(role_mode, lens, project_notes)]
    kb_block = build_kb_block(hit_dicts, entity_cards)

    history = _history_for_claude(conversation_id)
    # Inject the KB block as the very first user message of *this* turn
    # so it sits at a stable cache breakpoint. The actual user turn is
    # already at the tail of history.
    if not history or history[-1]["role"] != "user":
        # Defensive: caller should have appended the user message already.
        history.append({"role": "user", "content": user_redacted})

    # Prepend the KB block onto the *last* user turn.
    last_user = history[-1]
    if isinstance(last_user["content"], str):
        last_user["content"] = [
            kb_block,
            {"type": "text", "text": last_user["content"]},
        ]
    else:
        last_user["content"] = [kb_block, *last_user["content"]]

    # 4. Stream loop.
    client = get_client()
    citations: list[dict] = []
    final_text_parts: list[str] = []
    cumulative_blocks: list[dict] = []
    tokens_in = tokens_out = cache_read_in = cache_create_in = 0

    loop = asyncio.get_event_loop()

    def _run_stream():
        return client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=system_blocks,
            messages=history,
            tools=TOOL_SCHEMAS,
        )

    iteration = 0
    while True:
        iteration += 1
        if iteration > 8:
            log.warning("chat loop hit iteration cap (8)")
            publish(topic, "warning", {
                "message": "Tool-use loop capped at 8 iterations. "
                           "The response may be incomplete.",
            })
            break

        stream_cm = await loop.run_in_executor(None, _run_stream)
        # The Anthropic SDK's stream returns a context manager. We
        # iterate its sync events from a thread and bridge into asyncio.
        text_block_chunks: list[str] = []
        tool_calls: list[dict] = []
        any_text = False

        with stream_cm as stream:
            for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        text_block_chunks.append(delta.text)
                        any_text = True
                        publish(topic, "text_delta", {"text": delta.text})
                elif etype == "content_block_stop":
                    pass
                elif etype == "message_stop":
                    final = stream.get_final_message()
                    # Capture token usage from final usage block.
                    usage = getattr(final, "usage", None)
                    if usage:
                        tokens_in += getattr(usage, "input_tokens", 0) or 0
                        tokens_out += getattr(usage, "output_tokens", 0) or 0
                        cache_read_in += getattr(
                            usage, "cache_read_input_tokens", 0) or 0
                        cache_create_in += getattr(
                            usage, "cache_creation_input_tokens", 0) or 0
                    # Walk the final blocks to pick up any tool_use.
                    for block in (final.content or []):
                        bt = getattr(block, "type", None)
                        if bt == "text":
                            cumulative_blocks.append({
                                "type": "text",
                                "text": getattr(block, "text", ""),
                            })
                        elif bt == "tool_use":
                            tool_calls.append({
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            })
                            cumulative_blocks.append({
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            })

        if any_text:
            final_text_parts.append("".join(text_block_chunks))

        if not tool_calls:
            break

        # Execute tools, append tool_result, loop.
        assistant_with_tools = {"role": "assistant", "content": cumulative_blocks}
        history.append(assistant_with_tools)
        tool_results_blocks = []
        for call in tool_calls:
            publish(topic, "tool_use",
                    {"name": call["name"], "input": call["input"]})
            try:
                # Defense in depth: redact the tool result before it
                # goes back to Claude.
                raw = execute_tool(call["name"], call["input"])
                result_text = json.dumps(raw, default=str)
                redacted_result = apply_redactions(result_text).redacted_text
            except Exception as exc:
                log.exception("tool %s failed: %s", call["name"], exc)
                redacted_result = json.dumps({"error": "Tool execution failed."})
            publish(topic, "tool_result",
                    {"name": call["name"], "size": len(redacted_result)})
            tool_results_blocks.append({
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": redacted_result,
            })
            citations.append({"tool": call["name"],
                              "input": call["input"]})
        history.append({"role": "user", "content": tool_results_blocks})
        cumulative_blocks = []
        # Loop.

    # 5. Finalize.
    redacted_text = "\n\n".join(final_text_parts).strip() or \
                    "(no response)"
    # Only rehydrate placeholders that were actually present in the prompt
    # history Claude saw — prevents prompt-injection from forcing the
    # rehydration of arbitrary redaction_map entries.
    sent_placeholders = _used_placeholders(json.dumps(history, default=str))
    used = _used_placeholders(redacted_text) & sent_placeholders
    mapping = load_rehydration_map(used)
    display_text = rehydrate(redacted_text, mapping)

    citations.extend([
        {"chunk_id": h["chunk_id"],
         "document_id": h["document_id"],
         "section_path": h.get("section_path")}
        for h in hit_dicts[:5]
    ])

    msg_id = messages_store.append(
        conversation_id=conversation_id,
        role="assistant",
        content=cumulative_blocks if cumulative_blocks else
                [{"type": "text", "text": redacted_text}],
        redacted_view=redacted_text,
        display_view=display_text,
        citations=citations,
        tokens_in=tokens_in or None,
        tokens_out=tokens_out or None,
        cache_read_in=cache_read_in or None,
        cache_create_in=cache_create_in or None,
    )
    conv = conversations_store.get(conversation_id)
    if conv and not conv.get("title"):
        raw = user_text.strip().replace("\n", " ")
        auto_title = (raw[:60].rsplit(" ", 1)[0] if len(raw) > 60 else raw) or "New chat"
        conversations_store.touch(conversation_id, title=auto_title)
    else:
        conversations_store.touch(conversation_id)

    publish(topic, "done", {
        "message_id": msg_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_in": cache_read_in,
        "cache_create_in": cache_create_in,
        "citations_count": len(citations),
    })
    return msg_id
