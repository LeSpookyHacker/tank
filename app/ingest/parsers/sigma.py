"""Sigma detection-rule parser.

A Sigma rule is a YAML document describing a detection in a vendor-
agnostic schema. We parse the file, extract the rule metadata
(title, description, level, tags), and turn it into a `Detection`
entity + a single chunk for retrieval.

ATT&CK tags follow the `attack.txxxx` convention; the entity
extractor links them to `AttackTechnique` entities on ingest.
"""
from __future__ import annotations

from pathlib import Path

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:
    _HAVE_YAML = False

from app.ingest.parsers._base import ParsedDocument, ParsedSection, Parser


class SigmaParser(Parser):
    """Parse a single Sigma rule file (YAML)."""

    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta: dict = {"format": "sigma"}
        title = path.stem
        description = ""
        level = ""
        tags: list[str] = []
        rule_id = ""
        attack_ids: list[str] = []

        if _HAVE_YAML:
            try:
                doc = yaml.safe_load(raw) or {}
            except Exception:
                doc = {}
            if isinstance(doc, dict):
                title = doc.get("title") or title
                description = doc.get("description") or ""
                level = doc.get("level") or ""
                rule_id = doc.get("id") or ""
                tags = doc.get("tags") or []
                if isinstance(tags, list):
                    attack_ids = [
                        t.upper().replace("ATTACK.", "T").replace("ATTACK_", "T")
                        for t in tags
                        if isinstance(t, str) and t.lower().startswith("attack.")
                    ]
                    # normalize "attack.t1078" -> "T1078"
                    attack_ids = [
                        a if a.startswith("T") else f"T{a}"
                        for a in attack_ids
                    ]
                meta.update({
                    "sigma_id": rule_id,
                    "level": level,
                    "tags": tags,
                    "attack_ids": attack_ids,
                })
        else:
            description = raw[:2000]

        # One chunk with the rendered metadata so retrieval works even
        # without entity links.
        rendered = self._render(
            title=title, description=description, level=level,
            tags=tags, attack_ids=attack_ids, raw=raw,
        )
        sections = [ParsedSection(section_path="detection", text=rendered)]
        return ParsedDocument(
            kind="sigma", title=title, sections=sections, meta=meta,
        )

    def _render(self, *, title: str, description: str, level: str,
                tags: list, attack_ids: list[str], raw: str) -> str:
        lines = [f"# Detection: {title}", ""]
        if description:
            lines.extend([description, ""])
        if level:
            lines.append(f"**Severity:** {level}")
        if attack_ids:
            lines.append(f"**ATT&CK techniques:** {', '.join(attack_ids)}")
        if tags:
            lines.append(f"**Tags:** {', '.join(map(str, tags))}")
        lines.append("")
        lines.append("```yaml")
        lines.append(raw.strip())
        lines.append("```")
        return "\n".join(lines)
