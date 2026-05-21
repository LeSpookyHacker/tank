"""Per-format parsers.

Each parser exposes `parse(path: Path) -> ParsedDocument`. The pipeline
dispatches by file extension via `dispatch(path)`.
"""
from __future__ import annotations

from pathlib import Path

from app.ingest.parsers.control_framework import ControlFrameworkParser
from app.ingest.parsers.csv_json import CSVJSONParser
from app.ingest.parsers.docx import DocxParser
from app.ingest.parsers.iam import IAMParser
from app.ingest.parsers.image import ImageParser
from app.ingest.parsers.markdown import MarkdownParser
from app.ingest.parsers.pdf import PDFParser
from app.ingest.parsers.sigma import SigmaParser


_BY_EXT = {
    ".md": MarkdownParser,
    ".markdown": MarkdownParser,
    ".txt": MarkdownParser,
    ".pdf": PDFParser,
    ".docx": DocxParser,
    ".csv": CSVJSONParser,
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".webp": ImageParser,
    ".gif": ImageParser,
    # Phase 14 dedicated suffixes (used by the watcher dispatch hints).
    ".sigma": SigmaParser,
    ".sigma.yml": SigmaParser,
    ".sigma.yaml": SigmaParser,
}


def dispatch(path: Path):
    """Pick a parser for `path`.

    Extension is the first signal; for `.json` / `.yaml` we sniff
    content to distinguish IAM policies and control frameworks from
    generic CMDB-shaped data.
    """
    ext = path.suffix.lower()

    # JSON / YAML: content-sniff to disambiguate.
    if ext in (".json", ".yaml", ".yml"):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")[:4000]
        except Exception:
            raw = ""
        lowered = raw.lower()
        if '"statement"' in lowered or '"version": "2012-10-17"' in lowered:
            return IAMParser()
        if '"bindings"' in lowered and '"role"' in lowered:
            return IAMParser()
        if '"rules":' in lowered and ('"verbs"' in lowered
                                       or '"apigroups"' in lowered):
            return IAMParser()
        if '"framework"' in lowered or '"controls":' in lowered \
                or '"requirements":' in lowered:
            return ControlFrameworkParser()
        if ext in (".yaml", ".yml") and "logsource" in lowered \
                and "detection" in lowered:
            return SigmaParser()
        if ext == ".json":
            return CSVJSONParser()
        # default YAML: try Sigma if it has detection-like keys, else fall
        # through to the file-not-supported error below.
        if "detection" in lowered or "logsource" in lowered:
            return SigmaParser()

    cls = _BY_EXT.get(ext)
    if cls is None:
        raise ValueError(f"no parser for extension {ext!r} ({path})")
    return cls()
