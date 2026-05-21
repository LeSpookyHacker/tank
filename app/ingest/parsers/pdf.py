"""PDF parser via pypdf.

Each page becomes a section. Pages with very little extractable text
(<50 chars) are flagged for vision routing — for now they're just
skipped with a warning recorded in `meta`.
"""
from __future__ import annotations

from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


class PDFParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        sections: list[ParsedSection] = []
        skipped_pages: list[int] = []
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            text = text.strip()
            if len(text) < 50:
                skipped_pages.append(i + 1)
                continue
            sections.append(ParsedSection(
                section_path=f"page {i + 1}",
                text=text,
            ))

        meta: dict = {
            "size_bytes": path.stat().st_size,
            "page_count": len(reader.pages),
        }
        if skipped_pages:
            meta["pages_skipped_low_text"] = skipped_pages
        # Title heuristic: first non-empty line of page 1.
        title: str | None = None
        if sections:
            first_line = sections[0].text.splitlines()[0].strip() if sections[0].text else ""
            title = first_line[:120] if first_line else None
        return ParsedDocument(
            kind="pdf", title=title, sections=sections, meta=meta,
        )
