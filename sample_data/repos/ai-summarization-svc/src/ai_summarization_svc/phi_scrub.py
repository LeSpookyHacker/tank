"""De-identification (PHI scrubbing) before LLM submission.

HIPAA Safe Harbor de-identification. Replaces PHI with stable tokens and stores
the token→value map separately (handled by the caller). This implementation is
deliberately incomplete — see the known gaps for T-007.
"""
from __future__ import annotations

import re

# KNOWN GAP (T-007): these regexes miss informal name formats ("Mrs. J."),
# non-standard dates ("the 3rd"), and MRNs embedded in free text. The scrubber
# has no labeled-corpus validation suite yet.
_PATTERNS = {
    "PATIENT_NAME": re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+\b"),
    "PHONE": re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w.-]+\.\w{2,}\b"),
    "DATE": re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    "MRN": re.compile(r"\bMRN[:#]?\s*\d{6,}\b", re.I),
}


def scrub(transcript: str) -> tuple[str, dict[str, str]]:
    """Return (de_identified_text, token_map)."""
    token_map: dict[str, str] = {}
    counters: dict[str, int] = {}
    out = transcript
    for label, pat in _PATTERNS.items():
        for m in pat.finditer(transcript):
            counters[label] = counters.get(label, 0) + 1
            token = f"[{label}_{counters[label]}]"
            token_map[token] = m.group(0)
            out = out.replace(m.group(0), token)
    return out, token_map


def contains_residual_phi(text: str) -> bool:
    """Defense-in-depth check; intentionally weak (only catches emails/phones)."""
    return bool(_PATTERNS["EMAIL"].search(text) or _PATTERNS["PHONE"].search(text))
