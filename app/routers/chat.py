"""Chat HTTP + SSE endpoints."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.claude.chat import run_turn
from app.claude.event_bus import drain, subscribe, unsubscribe
from app.config import MODEL, TEMPLATES_DIR
from app.role import get_state
from app.storage import conversations_store, messages_store

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
log = logging.getLogger("tank.routers.chat")


class CreateConversation(BaseModel):
    role_mode: str | None = None
    title: str | None = None
    scope: dict | None = None


class PostMessage(BaseModel):
    content: str


# ---------------- HTML ----------------

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, conv: str | None = None):
    state = get_state()
    convs = conversations_store.list_recent(50)
    active = None
    messages = []
    if conv:
        active = conversations_store.get(conv)
        if active:
            messages = messages_store.list_for_conv(conv)
    return templates.TemplateResponse(
        request=request, name="chat.html",
        context={
            "state": state, "conversations": convs,
            "active": active, "messages": messages,
        },
    )


# ---------------- API ----------------

@router.post("/api/conversations")
async def create_conversation(body: CreateConversation) -> dict:
    state = get_state()
    role_mode = body.role_mode or state.role_mode.value
    conv_id = conversations_store.create(
        role_mode=role_mode, model=MODEL,
        title=body.title, scope=body.scope or {},
    )
    return {"id": conv_id}


@router.get("/api/conversations")
async def list_conversations() -> dict:
    return {"conversations": conversations_store.list_recent(50)}


@router.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str) -> dict:
    conv = conversations_store.get(conv_id)
    if not conv:
        raise HTTPException(404, "no such conversation")
    msgs = messages_store.list_for_conv(conv_id)
    return {"conversation": conv, "messages": msgs}


@router.post("/api/conversations/{conv_id}/messages")
async def post_message(conv_id: str, body: PostMessage) -> dict:
    conv = conversations_store.get(conv_id)
    if not conv:
        raise HTTPException(404, "no such conversation")

    # Persist the user message immediately (redacted_view + display_view
    # set so the UI can show it without waiting for round-trip).
    from app.redact.engine import apply_redactions
    red = apply_redactions(body.content)
    user_msg_id = messages_store.append(
        conversation_id=conv_id, role="user",
        content=body.content,
        redacted_view=red.redacted_text,
        display_view=body.content,
    )

    # Kick off the assistant turn in a background task.
    asyncio.create_task(_run_turn_safely(conv_id, body.content))
    return {"user_message_id": user_msg_id}


async def _run_turn_safely(conv_id: str, user_text: str):
    try:
        await run_turn(conv_id, user_text)
    except Exception as exc:
        log.exception("turn failed for %s", conv_id)
        from app.claude.event_bus import publish
        publish(f"chat.{conv_id}", "error", {"error": str(exc)})


@router.get("/api/conversations/{conv_id}/stream")
async def stream(conv_id: str):
    """SSE stream of events for a conversation.

    Events: text_delta, tool_use, tool_result, done, error.
    """
    if not conversations_store.get(conv_id):
        raise HTTPException(404, "no such conversation")

    topic = f"chat.{conv_id}"
    q = subscribe(topic)

    async def event_source():
        try:
            async for ev in drain(q, idle_timeout=15.0):
                if ev is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {
                    "event": ev.kind,
                    "data": json.dumps(ev.payload, default=str),
                }
                if ev.kind in {"done", "error"}:
                    break
        finally:
            unsubscribe(topic, q)

    return EventSourceResponse(event_source())
