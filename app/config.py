from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT_DIR / "prompts"
APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

# Primary model for reports, chat, vision, and complex reasoning.
MODEL = "claude-sonnet-4-6"

# Cheaper model for structured-extraction tasks with predictable schemas.
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Set TANK_DEBUG_TOKENS=1 to log per-call token usage to the console.
DEBUG_TOKENS = os.environ.get("TANK_DEBUG_TOKENS", "").lower() in ("1", "true", "on")

# Read once at import so the rest of the app can rely on these.
INTERNAL_TLD = os.getenv("TANK_INTERNAL_TLD", "").strip().lower()
ENABLE_PERSON_REDACTION = os.getenv("TANK_ENABLE_PERSON_REDACTION", "").strip() == "1"
ENV = os.getenv("TANK_ENV", "dev").strip().lower()
DIGEST_TIME = os.getenv("TANK_DIGEST_TIME", "08:00").strip()

_log = logging.getLogger("tank.tokens")


@lru_cache
def get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    # max_retries: the SDK retries 5xx / 429 / connection errors with
    # exponential backoff. We bump from the default (2) to handle the
    # transient blips you get on a corporate VPN or during Anthropic
    # rolling deploys.
    # timeout: per-request ceiling. Default is 10 min, which is fine
    # for the longest report generations but never wants to be unbounded.
    return Anthropic(
        api_key=api_key,
        max_retries=int(os.environ.get("TANK_API_MAX_RETRIES", "4")),
        timeout=float(os.environ.get("TANK_API_TIMEOUT_SECONDS", "600")),
    )


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def log_token_usage(call_site: str, model: str, usage) -> None:
    """Record per-call token usage to the api_calls table and optionally log.

    `usage` may be an Anthropic Usage object or a dict with keys
    tokens_in / tokens_out / cache_read_in / cache_create_in.
    """
    if usage is None:
        return
    if isinstance(usage, dict):
        ti  = usage.get("tokens_in", 0) or 0
        to_ = usage.get("tokens_out", 0) or 0
        cr  = usage.get("cache_read_in", 0) or 0
        cc  = usage.get("cache_create_in", 0) or 0
    else:
        ti  = getattr(usage, "input_tokens", 0) or 0
        to_ = getattr(usage, "output_tokens", 0) or 0
        cr  = getattr(usage, "cache_read_input_tokens", 0) or 0
        cc  = getattr(usage, "cache_creation_input_tokens", 0) or 0

    if DEBUG_TOKENS:
        _log.info("[tokens] site=%s model=%s in=%d out=%d cr=%d cc=%d",
                  call_site, model, ti, to_, cr, cc)

    try:
        from app.storage import api_calls_store
        api_calls_store.record(
            call_site=call_site, model=model,
            tokens_in=ti, tokens_out=to_,
            cache_read_in=cr, cache_create_in=cc,
        )
    except Exception:
        _log.debug("api_calls_store.record failed — DB not ready yet", exc_info=True)
