from __future__ import annotations

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

# One model for everything: extraction, chat, reports, vision, nudges, notes.
MODEL = "claude-sonnet-4-6"

# Read once at import so the rest of the app can rely on these.
INTERNAL_TLD = os.getenv("TANK_INTERNAL_TLD", "").strip().lower()
ENABLE_PERSON_REDACTION = os.getenv("TANK_ENABLE_PERSON_REDACTION", "").strip() == "1"
ENV = os.getenv("TANK_ENV", "dev").strip().lower()
DIGEST_TIME = os.getenv("TANK_DIGEST_TIME", "08:00").strip()


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
