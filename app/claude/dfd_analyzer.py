"""STRIDE threat modeling for Data Flow Diagrams.

Accepts Mermaid source or raw image bytes. Results are cached by SHA-256
of the input so re-submitting the same diagram costs nothing.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from app.config import MODEL, get_client, load_prompt, log_token_usage
from app.schemas import DFDAnalysis, DFDImprovement
from app.storage import dfd_store

log = logging.getLogger("tank.dfd")


def _hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def analyze_mermaid(mermaid_src: str, force: bool = False) -> tuple[str, DFDAnalysis]:
    """Run STRIDE analysis on a Mermaid DFD string.

    Returns (dfd_id, analysis). Cached by diagram hash unless force=True.
    """
    diagram_hash = _hash(mermaid_src)
    if not force:
        cached = dfd_store.get_by_hash(diagram_hash)
        if cached:
            log.info("dfd cache hit for %s", diagram_hash[:12])
            return cached["id"], _dict_to_analysis(cached["analysis"])

    prompt = load_prompt("dfd_stride")
    client = get_client()
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": "Analyze this Mermaid DFD with STRIDE:\n\n```mermaid\n"
                             + mermaid_src + "\n```"},
                ],
            }],
            output_format=DFDAnalysis,
        )
        log_token_usage("dfd.analyze_mermaid", MODEL, getattr(resp, "usage", None))
        usage = getattr(resp, "usage", None)
        parsed: DFDAnalysis = getattr(resp, "parsed_output", None) or DFDAnalysis()
    except Exception as exc:
        log.warning("DFD analysis failed: %s", exc)
        parsed = DFDAnalysis()
        usage = None

    analysis_dict = parsed.model_dump()
    dfd_id = dfd_store.insert(
        diagram_hash=diagram_hash,
        mermaid_src=mermaid_src,
        analysis_json=analysis_dict,
        tokens_in=getattr(usage, "input_tokens", None) if usage else None,
        tokens_out=getattr(usage, "output_tokens", None) if usage else None,
    )
    return dfd_id, parsed


def analyze_image(image_bytes: bytes, media_type: str = "image/png") -> tuple[str, DFDAnalysis]:
    """Run STRIDE analysis on a DFD image using Claude vision."""
    diagram_hash = _hash(image_bytes)
    cached = dfd_store.get_by_hash(diagram_hash)
    if cached:
        log.info("dfd image cache hit for %s", diagram_hash[:12])
        return cached["id"], _dict_to_analysis(cached["analysis"])

    prompt = load_prompt("dfd_stride")
    client = get_client()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64",
                                "media_type": media_type, "data": b64}},
                    {"type": "text",
                     "text": "Analyze this DFD image with STRIDE. "
                             "Generate a Mermaid representation and annotate it."},
                ],
            }],
            output_format=DFDAnalysis,
        )
        log_token_usage("dfd.analyze_image", MODEL, getattr(resp, "usage", None))
        usage = getattr(resp, "usage", None)
        parsed: DFDAnalysis = getattr(resp, "parsed_output", None) or DFDAnalysis()
    except Exception as exc:
        log.warning("DFD image analysis failed: %s", exc)
        parsed = DFDAnalysis()
        usage = None

    analysis_dict = parsed.model_dump()
    dfd_id = dfd_store.insert(
        diagram_hash=diagram_hash,
        mermaid_src=parsed.annotated_mermaid or None,
        analysis_json=analysis_dict,
        tokens_in=getattr(usage, "input_tokens", None) if usage else None,
        tokens_out=getattr(usage, "output_tokens", None) if usage else None,
    )
    return dfd_id, parsed


def improve_mermaid(mermaid_src: str, kb_context: str = "") -> DFDImprovement:
    """Ask Claude to complete an incomplete DFD using KB context.

    Returns DFDImprovement with improved_mermaid and a suggestions list.
    Does not cache — each improve call is intentionally fresh.
    """
    prompt = load_prompt("dfd_improve")
    client = get_client()
    user_parts: list[dict] = []
    if kb_context:
        user_parts.append({
            "type": "text",
            "text": f"## Knowledge base context\n\n{kb_context}",
            "cache_control": {"type": "ephemeral"},
        })
    user_parts.append({
        "type": "text",
        "text": "Improve this incomplete DFD:\n\n```mermaid\n" + mermaid_src + "\n```",
    })
    try:
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_parts}],
            output_format=DFDImprovement,
        )
        log_token_usage("dfd.improve_mermaid", MODEL, getattr(resp, "usage", None))
        parsed: DFDImprovement = getattr(resp, "parsed_output", None) or DFDImprovement()
    except Exception as exc:
        log.warning("DFD improve failed: %s", exc)
        parsed = DFDImprovement(
            improved_mermaid=mermaid_src,
            suggestions=["Improvement failed — returned original diagram unchanged."],
        )
    return parsed


def _dict_to_analysis(d: dict) -> DFDAnalysis:
    try:
        return DFDAnalysis(**d)
    except Exception:
        return DFDAnalysis()
