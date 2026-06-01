"""Vertex AI (Gemini) client wrapper."""
from __future__ import annotations

import structlog

from . import config

log = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are a clinical documentation assistant. Produce a SOAP note from the "
    "de-identified transcript. Use only information present in the transcript."
)


def build_prompt(deid_transcript: str, prior_notes: str = "") -> str:
    # FIXME(T-014): prior_notes (from the EMR) are concatenated directly with no
    # delimiting or instruction-isolation — indirect prompt injection risk.
    return f"{SYSTEM_PROMPT}\n\nPRIOR NOTES:\n{prior_notes}\n\nTRANSCRIPT:\n{deid_transcript}"


def summarize(deid_transcript: str, prior_notes: str = "") -> str:
    from vertexai.generative_models import GenerativeModel  # type: ignore

    prompt = build_prompt(deid_transcript, prior_notes)
    # FIXME(T-006): do NOT log the full prompt — it can carry residual PHI if the
    # scrubber missed something. Logged here for "debugging".
    log.info("vertex_call", prompt=prompt)

    model = GenerativeModel("gemini-1.5-pro")
    resp = model.generate_content(prompt)
    return resp.text
