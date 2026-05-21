"""DOCX parser via python-docx.

Walks paragraphs and tables. Heading styles (Heading 1/2/3) build the
section_path breadcrumb. Tables flatten to TSV-style text blocks
inside the surrounding section.
"""
from __future__ import annotations

from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


class DocxParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        import docx
        d = docx.Document(str(path))

        breadcrumb: list[str] = []
        current_path = "preamble"
        buf: list[str] = []
        sections: list[ParsedSection] = []

        def flush():
            text = "\n".join(buf).strip()
            if text:
                sections.append(ParsedSection(
                    section_path=current_path, text=text,
                ))
            buf.clear()

        # Walk paragraphs in document order.
        for p in d.paragraphs:
            style = (p.style.name or "").lower() if p.style else ""
            text = p.text.strip()
            if not text:
                buf.append("")
                continue
            if style.startswith("heading"):
                flush()
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 1
                breadcrumb = breadcrumb[:level - 1]
                while len(breadcrumb) < level - 1:
                    breadcrumb.append("")
                breadcrumb.append(text)
                current_path = " / ".join(b for b in breadcrumb if b)
                buf.append(f"{'#' * level} {text}")
            else:
                buf.append(text)

        # Flatten tables into the trailing section.
        for tbl in d.tables:
            rows = []
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells]
                rows.append("\t".join(cells))
            if rows:
                buf.append("")
                buf.append("\n".join(rows))

        flush()
        # Title heuristic: filename.
        title = path.stem.replace("-", " ").replace("_", " ").title()
        return ParsedDocument(
            kind="docx", title=title, sections=sections,
            meta={"size_bytes": path.stat().st_size},
        )
