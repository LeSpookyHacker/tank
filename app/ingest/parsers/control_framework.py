"""Control-framework parser (CIS Controls v8, NIST 800-53, SOC2 CC).

The user uploads a framework JSON dump. The shape is loosely
normalized to a list of `{control_id, title, description, family,
subcontrols?}`. We ingest each control as a `Control` entity with a
linked chunk so retrieval can match user phrasing to controls.

The Phase-14 compliance helper iterates these and asks Sonnet to
find evidence in the KB for each one.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


class ControlFrameworkParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            doc = json.loads(raw)
        except Exception:
            doc = {}

        controls = self._normalize(doc)
        title = (
            doc.get("framework")
            or doc.get("name")
            or path.stem.replace("_", " ").title()
        )
        sections: list[ParsedSection] = []
        sections.append(ParsedSection(
            section_path="framework",
            text=f"# {title}\n\n{len(controls)} controls.",
        ))
        for c in controls:
            section_path = f"{c['control_id']}"
            body = (
                f"## {c['control_id']}: {c['title']}\n\n"
                f"Family: {c.get('family', '—')}\n\n"
                f"{c.get('description', '')}"
            )
            if c.get("subcontrols"):
                body += "\n\n### Subcontrols\n"
                for sc in c["subcontrols"]:
                    body += f"- {sc.get('id', '?')}: {sc.get('title', '')}\n"
            sections.append(ParsedSection(section_path=section_path, text=body))

        return ParsedDocument(
            kind="control_framework", title=title, sections=sections,
            meta={"framework": title, "control_count": len(controls)},
        )

    def _normalize(self, doc) -> list[dict]:
        """Try to find a list of controls under common keys."""
        if isinstance(doc, list):
            items = doc
        elif isinstance(doc, dict):
            for key in ("controls", "items", "requirements", "ccs"):
                if key in doc and isinstance(doc[key], list):
                    items = doc[key]
                    break
            else:
                items = []
        else:
            items = []

        out = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            out.append({
                "control_id": str(
                    raw.get("id") or raw.get("control_id")
                    or raw.get("ref") or "?"
                ),
                "title": str(raw.get("title") or raw.get("name") or ""),
                "description": str(raw.get("description")
                                   or raw.get("summary") or ""),
                "family": str(raw.get("family")
                              or raw.get("category") or ""),
                "subcontrols": raw.get("subcontrols") or [],
            })
        return out
