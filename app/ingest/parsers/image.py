"""Image parser via Claude Sonnet 4.6 vision.

Diagrams and architecture screenshots get base64-encoded and sent to
Claude with the extract_arch_diagram.md prompt. Sonnet 4.6 is natively
multimodal — the image block format is the same shape as PDF.

The parsed text is the diagram summary; entity/edge extraction is the
side-effect that the extractor module picks up. To keep parser API
uniform, we stash the structured extraction in `meta["vision"]`.
"""
from __future__ import annotations

import base64
from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser

_MEDIA_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB


class ImageParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        size = path.stat().st_size
        if size > _MAX_IMAGE_BYTES:
            return ParsedDocument(
                kind="image", title=path.stem,
                sections=[ParsedSection(
                    section_path="diagram",
                    text="(image too large for vision analysis — max 20 MB)",
                )],
                meta={"size_bytes": size, "skipped": True},
            )
        media_type = _MEDIA_BY_EXT.get(path.suffix.lower(), "image/png")
        b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")

        extraction = self._call_vision(b64, media_type)
        summary = extraction.get("diagram_summary", "")
        # Append any entity/edge mentions as quasi-prose so they
        # surface in keyword + vector retrieval too.
        text_lines = [summary] if summary else []
        for ent in extraction.get("entities", []):
            text_lines.append(
                f"Entity: {ent.get('type','?')} '{ent.get('name','?')}'"
                + (f" — {ent['description']}" if ent.get("description") else "")
            )
        for edge in extraction.get("relationships", []):
            text_lines.append(
                f"Edge: {edge.get('src_name','?')} "
                f"--{edge.get('kind','?')}--> {edge.get('dst_name','?')}"
            )
        text = "\n".join(text_lines) or "(empty diagram extraction)"

        return ParsedDocument(
            kind="image", title=path.stem,
            sections=[ParsedSection(section_path="diagram", text=text)],
            meta={
                "size_bytes": path.stat().st_size,
                "media_type": media_type,
                "vision": extraction,
            },
        )

    def _call_vision(self, b64: str, media_type: str) -> dict:
        from app.claude.extractor import extract_from_diagram
        return extract_from_diagram(b64, media_type)
