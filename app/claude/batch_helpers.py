"""Structured-output adapters for the Anthropic Message Batches API.

The Batches endpoint accepts raw `messages.create` params — no
`output_format=PydanticClass` typed parse. To get a Pydantic-shaped
response from a batch, we force a single tool call whose `input_schema`
is the Pydantic class's JSON schema, then read `tool_use.input` from
the message content.

Two helpers, both pure / dependency-light so they stay easy to unit-test:

- `tool_params_for(cls)` builds the `tools=[...]` and `tool_choice=...`
  fragments to inject into a batch request's `params`.
- `extract_validated(msg, cls)` walks a returned `Message.content` for
  the tool_use block and validates its `.input` against the class.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

log = logging.getLogger("tank.batch_helpers")


def _tool_name_for(cls: type[BaseModel]) -> str:
    """Default tool name: `emit_<class_lower>`. Anthropic requires
    `^[a-zA-Z0-9_-]{1,64}$`, which `BaseModel` subclass names always
    satisfy after lowercasing."""
    return f"emit_{cls.__name__.lower()}"


def tool_params_for(
    cls: type[BaseModel],
    name: str | None = None,
) -> tuple[list[dict], dict]:
    """Build (tools, tool_choice) for forcing a single structured response.

    Usage in a batch request `params` dict:

        tools, tool_choice = tool_params_for(MeetingPrepBrief)
        params = {
            "model": HAIKU_MODEL,
            "max_tokens": 4096,
            "system": [...],
            "messages": [...],
            "tools": tools,
            "tool_choice": tool_choice,
        }
    """
    tool_name = name or _tool_name_for(cls)
    schema = cls.model_json_schema()
    description = (
        f"Emit a structured {cls.__name__} payload. This is the only "
        f"way to return a result; do not write prose."
    )
    tools = [{
        "name": tool_name,
        "description": description,
        "input_schema": schema,
    }]
    tool_choice = {"type": "tool", "name": tool_name}
    return tools, tool_choice


def extract_validated(msg: Any, cls: type[BaseModel]) -> BaseModel | None:
    """Pull the forced-tool-call input out of `msg.content` and validate.

    Returns `None` and logs a warning if no tool_use block is present
    (shouldn't happen when `tool_choice` forces it, but the Anthropic
    contract is "may return text instead under certain error paths").
    """
    blocks = getattr(msg, "content", None) or []
    for block in blocks:
        btype = getattr(block, "type", None)
        if btype == "tool_use":
            payload = getattr(block, "input", None)
            if payload is None:
                log.warning("tool_use block missing .input for %s",
                            cls.__name__)
                return None
            try:
                return cls.model_validate(payload)
            except ValidationError as exc:
                log.warning("tool_use input failed %s validation: %s",
                            cls.__name__, exc)
                return None
    log.warning("no tool_use block in message content for %s; "
                "got %d block(s) of types %r",
                cls.__name__, len(blocks),
                [getattr(b, "type", None) for b in blocks])
    return None
