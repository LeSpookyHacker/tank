"""CSV / JSON parser for CMDB-shaped data.

For CSV: each row → a small ParsedSection so the chunker keeps rows
together. For JSON: arrays of records get the same treatment; scalar
JSON gets one section.

Column mapping for CMDB-aware entity extraction is handled in the
Phase-5 extractor (extract_cmdb_row prompt); this parser is shape-
agnostic — it just gets the text into the pipeline.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


class CSVJSONParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        ext = path.suffix.lower()
        if ext == ".csv":
            return self._parse_csv(path)
        elif ext == ".json":
            return self._parse_json(path)
        raise ValueError(f"CSVJSONParser cannot handle {ext}")

    def _parse_csv(self, path: Path) -> ParsedDocument:
        sections: list[ParsedSection] = []
        meta: dict = {"size_bytes": path.stat().st_size}
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            meta["columns"] = reader.fieldnames or []
            rows = list(reader)
        meta["row_count"] = len(rows)

        # Header section so the chunker can give the LLM column context.
        header_text = "Columns: " + ", ".join(meta["columns"])
        sections.append(ParsedSection(section_path="columns", text=header_text))

        # Group rows into chunks of 25 so we get a few rows per chunk
        # rather than 1 row per chunk (faster + more context per call).
        for batch_start in range(0, len(rows), 25):
            batch = rows[batch_start:batch_start + 25]
            lines = []
            for r in batch:
                kv = ", ".join(f"{k}={v}" for k, v in r.items() if v)
                lines.append(kv)
            sections.append(ParsedSection(
                section_path=f"rows {batch_start + 1}-{batch_start + len(batch)}",
                text="\n".join(lines),
            ))

        return ParsedDocument(
            kind="csv", title=path.stem,
            sections=sections, meta=meta,
        )

    def _parse_json(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # Fall back: treat as a single text blob.
            return ParsedDocument(
                kind="json", title=path.stem,
                sections=[ParsedSection(section_path="raw", text=raw)],
                meta={"size_bytes": path.stat().st_size,
                      "parse_error": str(exc)},
            )

        sections: list[ParsedSection] = []
        if isinstance(data, list):
            for i, item in enumerate(data):
                sections.append(ParsedSection(
                    section_path=f"item {i}",
                    text=json.dumps(item, indent=2),
                ))
        else:
            sections.append(ParsedSection(
                section_path="root",
                text=json.dumps(data, indent=2),
            ))

        return ParsedDocument(
            kind="json", title=path.stem, sections=sections,
            meta={"size_bytes": path.stat().st_size},
        )
