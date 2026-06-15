"""Redaction layer.

Every byte sent to Claude passes through `engine.apply_redactions()`.
Originals stay on this machine in `redaction_map`; placeholders go out;
responses are rehydrated locally on the way back.

Public API:
    from app.redact import apply_redactions, rehydrate
"""

from app.redact.engine import apply_redactions, rehydrate, used_placeholders

__all__ = ["apply_redactions", "rehydrate", "used_placeholders"]
