"""Synthesize binary fixture artifacts from markdown sources.

Most demo content is plain markdown. A few items need to be PDF or
DOCX (so Tank's PDF/DOCX parsers get exercised). One needs a PNG (so
the vision parser gets exercised). This script generates those binary
artifacts from the markdown sources that live alongside them.

Sources & outputs:
  architecture/01-platform-overview.md  →  architecture/01-platform-overview.pdf
  architecture/02-auth-flow.md          →  architecture/02-auth-flow.png  (text-art PNG)
  policies/access-policy.md             →  policies/access-policy.docx

Run with the tank venv activated:
    python -m scripts._gen_fixtures
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


# ---------------- PDF ----------------

def md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    """Render markdown to a simple multi-page PDF.

    We don't need pretty typography — we need text Tank's pypdf-based
    parser can extract back out. A monospace, fixed-width layout is
    plenty.
    """
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject,
        FloatObject, NameObject, NumberObject, RectangleObject,
        TextStringObject,
    )

    text = md_path.read_text(encoding="utf-8")

    # Layout constants (US Letter, in PDF points; 72 pts = 1 inch)
    page_w, page_h = 612, 792
    margin_x, margin_y = 54, 54
    line_height = 12
    font_size = 9
    max_chars_per_line = 88
    max_lines_per_page = (page_h - 2 * margin_y) // line_height

    # Wrap long lines.
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            wrapped.append("")
            continue
        while len(raw_line) > max_chars_per_line:
            cut = raw_line.rfind(" ", 0, max_chars_per_line)
            if cut <= 0:
                cut = max_chars_per_line
            wrapped.append(raw_line[:cut])
            raw_line = raw_line[cut:].lstrip()
        wrapped.append(raw_line)

    writer = PdfWriter()

    # We'll build pages by hand to keep the PDF small and pypdf-extractable.
    for page_start in range(0, len(wrapped), max_lines_per_page):
        page_lines = wrapped[page_start:page_start + max_lines_per_page]

        # Build the content stream.
        cmds: list[str] = ["BT", f"/F1 {font_size} Tf"]
        cursor_y = page_h - margin_y
        cmds.append(f"{margin_x} {cursor_y} Td")
        for line in page_lines:
            # Escape parens and backslashes per PDF spec.
            safe = (line.replace("\\", "\\\\")
                        .replace("(", "\\(")
                        .replace(")", "\\)"))
            cmds.append(f"({safe}) Tj")
            cmds.append(f"0 -{line_height} Td")
        cmds.append("ET")
        content_str = "\n".join(cmds)

        content = DecodedStreamObject()
        content.set_data(content_str.encode("latin-1", errors="replace"))

        font_obj = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Courier"),
        })
        resources = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_obj}),
        })
        page_obj = DictionaryObject({
            NameObject("/Type"): NameObject("/Page"),
            NameObject("/MediaBox"): RectangleObject([0, 0, page_w, page_h]),
            NameObject("/Resources"): resources,
            NameObject("/Contents"): content,
        })

        # pypdf needs an indirect reference for /Contents; let it figure that
        # out by going through .add_page.
        from pypdf import PageObject
        page = PageObject(pdf=writer)
        page.update(page_obj)
        writer.add_page(page)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with pdf_path.open("wb") as f:
        writer.write(f)
    print(f"PDF: {pdf_path.relative_to(ROOT)} ({pdf_path.stat().st_size} bytes)")


# ---------------- DOCX ----------------

def md_to_docx(md_path: Path, docx_path: Path) -> None:
    """Render markdown to a basic DOCX with heading + paragraph styles.

    No fancy markdown parsing — `#`/`##`/`###` map to headings, lines
    starting with `-` map to a bullet list, fenced code blocks map to
    monospace, everything else is a paragraph.
    """
    from docx import Document
    from docx.shared import Pt

    text = md_path.read_text(encoding="utf-8")
    doc = Document()

    in_code = False
    in_list = False

    for raw in text.splitlines():
        line = raw.rstrip()

        if line.startswith("```"):
            in_code = not in_code
            in_list = False
            continue

        if in_code:
            p = doc.add_paragraph(line)
            for run in p.runs:
                run.font.name = "Courier New"
                run.font.size = Pt(9)
            continue

        if line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=1)
            in_list = False
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
            in_list = False
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
            in_list = False
        elif line.startswith("- "):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
            in_list = True
        elif not line:
            in_list = False
            doc.add_paragraph("")
        else:
            doc.add_paragraph(line)

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    print(f"DOCX: {docx_path.relative_to(ROOT)} ({docx_path.stat().st_size} bytes)")


# ---------------- PNG (text-art diagram) ----------------

def md_to_diagram_png(md_path: Path, png_path: Path) -> None:
    """Render the auth-flow diagram source to a simple PNG.

    The PNG is intentionally text-art-style — we don't need pretty,
    we need pixels that Tank's vision parser can convert back into
    entities + edges via Claude. We use PIL since it's a transitive
    dep of sentence-transformers (which is already in requirements.txt).
    """
    from PIL import Image, ImageDraw, ImageFont

    text = md_path.read_text(encoding="utf-8")

    # Pull the mermaid block out of the markdown — that's the diagram.
    lines: list[str] = []
    in_mermaid = False
    for raw in text.splitlines():
        if raw.strip().startswith("```mermaid"):
            in_mermaid = True
            continue
        if in_mermaid and raw.strip().startswith("```"):
            break
        if in_mermaid:
            lines.append(raw)

    if not lines:
        lines = text.splitlines()[:30]

    # Add a title and a small footer so the PNG has context.
    title = "Helix Robotics — Customer-side OAuth2 + service auth"
    lines = [title, "=" * len(title), ""] + lines

    # Choose a monospace font; fall back to default if unavailable.
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
    except OSError:
        font = ImageFont.load_default()

    line_height = 18
    padding = 24
    char_w = 9  # rough — Menlo at 14pt
    max_line_chars = max((len(line) for line in lines), default=60)
    width = padding * 2 + max_line_chars * char_w
    height = padding * 2 + len(lines) * line_height

    img = Image.new("RGB", (max(width, 400), max(height, 200)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((padding, padding + i * line_height), line, fill="black", font=font)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(png_path, "PNG")
    print(f"PNG: {png_path.relative_to(ROOT)} ({png_path.stat().st_size} bytes)")


# ---------------- driver ----------------

JOBS = [
    ("pdf",     "architecture/01-platform-overview.md", "architecture/01-platform-overview.pdf"),
    ("png",     "architecture/02-auth-flow.md",         "architecture/02-auth-flow.png"),
    ("docx",    "policies/access-policy.md",            "policies/access-policy.docx"),
]


def main(argv: list[str]) -> int:
    force = "--force" in argv
    for kind, src_rel, dst_rel in JOBS:
        src = FIXTURES / src_rel
        dst = FIXTURES / dst_rel
        if not src.exists():
            print(f"SKIP {dst_rel}: source {src_rel} missing", file=sys.stderr)
            continue
        if dst.exists() and not force:
            print(f"SKIP {dst_rel}: already exists (use --force to regenerate)")
            continue
        if kind == "pdf":
            md_to_pdf(src, dst)
        elif kind == "docx":
            md_to_docx(src, dst)
        elif kind == "png":
            md_to_diagram_png(src, dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
