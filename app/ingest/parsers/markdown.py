"""Markdown parser.

Walks the document by headings; each section's text becomes a
ParsedSection with `section_path` = breadcrumb of heading levels.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MarkdownParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        title = self._extract_title(raw, path)
        sections = self._split_by_heading(raw)
        return ParsedDocument(
            kind="md", title=title, sections=sections,
            meta={"size_bytes": path.stat().st_size},
        )

    def _extract_title(self, raw: str, path: Path) -> str:
        for line in raw.splitlines():
            m = _HEADING_RE.match(line)
            if m and len(m.group(1)) == 1:
                return m.group(2).strip()
        return path.stem.replace("_", " ").replace("-", " ").title()

    def _split_by_heading(self, raw: str) -> list[ParsedSection]:
        sections: list[ParsedSection] = []
        breadcrumb: list[str] = []
        buf: list[str] = []
        current_path = "preamble"
        for line in raw.splitlines():
            m = _HEADING_RE.match(line)
            if m:
                # Emit any buffered text under the previous heading.
                text = "\n".join(buf).strip()
                if text:
                    sections.append(ParsedSection(
                        section_path=current_path, text=text,
                    ))
                buf = []
                level = len(m.group(1))
                title = m.group(2).strip()
                # Update breadcrumb: drop any deeper-level entries, push this.
                breadcrumb = breadcrumb[:level - 1]
                while len(breadcrumb) < level - 1:
                    breadcrumb.append("")
                breadcrumb.append(title)
                current_path = " / ".join(b for b in breadcrumb if b)
                # Include the heading itself in the section text for context.
                buf.append(line)
            else:
                buf.append(line)
        text = "\n".join(buf).strip()
        if text:
            sections.append(ParsedSection(section_path=current_path, text=text))
        return sections
