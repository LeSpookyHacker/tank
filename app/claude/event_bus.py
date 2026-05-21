"""In-process pub/sub for live UI updates.

Each subscriber gets its own asyncio.Queue. Publishers fan-out events
to every queue registered for a topic. When the last subscriber for a
topic disconnects, the topic is removed entirely — no growing dict
across long uptimes.

Multi-tab safe: opening the same conversation in two browser tabs
gives each tab its own queue, so both see the streaming reply instead
of racing for `get()`.

Backwards-compat: `queue_for(topic)` still exists and registers a
fresh subscriber queue. Treat it as deprecated — new callers should
use `subscribe(topic)` + `unsubscribe(topic, q)` for explicit
lifetimes.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("tank.event_bus")

_TOPIC_SUBSCRIBERS: dict[str, list[asyncio.Queue]] = {}
_GLOBAL_SUBSCRIBERS: list[asyncio.Queue] = []


@dataclass
class Event:
    topic: str
    kind: str
    payload: Any


# ---------------- subscribe / unsubscribe ----------------

def subscribe(topic: str, *, maxsize: int = 1024) -> asyncio.Queue:
    """Register a new subscriber for `topic` and return its queue.

    Call `unsubscribe(topic, q)` when done — the SSE consumer should
    do this in a `finally` block so abandoned tabs don't pin memory.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    _TOPIC_SUBSCRIBERS.setdefault(topic, []).append(q)
    return q


def unsubscribe(topic: str, q: asyncio.Queue) -> None:
    subs = _TOPIC_SUBSCRIBERS.get(topic)
    if not subs:
        return
    try:
        subs.remove(q)
    except ValueError:
        return
    if not subs:
        # Last consumer left — drop the topic so the dict doesn't grow.
        _TOPIC_SUBSCRIBERS.pop(topic, None)


def subscriber_count(topic: str) -> int:
    return len(_TOPIC_SUBSCRIBERS.get(topic, ()))


def subscribe_global(*, maxsize: int = 1024) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    _GLOBAL_SUBSCRIBERS.append(q)
    return q


def unsubscribe_global(q: asyncio.Queue) -> None:
    try:
        _GLOBAL_SUBSCRIBERS.remove(q)
    except ValueError:
        pass


# ---------------- publish ----------------

def publish(topic: str, kind: str, payload: Any) -> None:
    ev = Event(topic=topic, kind=kind, payload=payload)
    # Snapshot — a queue could be removed mid-iteration if the consumer
    # just disconnected.
    for q in list(_TOPIC_SUBSCRIBERS.get(topic, ())):
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            log.warning("subscriber queue full for topic=%s, dropping", topic)
    for q in list(_GLOBAL_SUBSCRIBERS):
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            pass


# ---------------- drain helper ----------------

async def drain(q: asyncio.Queue, *, idle_timeout: float = 30.0):
    """Yield events from `q`; emit None on idle (for SSE heartbeat)."""
    while True:
        try:
            ev = await asyncio.wait_for(q.get(), timeout=idle_timeout)
            yield ev
        except asyncio.TimeoutError:
            yield None


# ---------------- legacy compatibility ----------------

def queue_for(topic: str) -> asyncio.Queue:
    """Deprecated: equivalent to `subscribe(topic)`. Returns a fresh
    queue every call. Callers that want explicit cleanup should use
    `subscribe()` + `unsubscribe()` directly.
    """
    return subscribe(topic)
