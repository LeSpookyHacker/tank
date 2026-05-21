"""Shared parser types."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ParsedSection:
    section_path: str
    text: str


@dataclass
class ParsedDocument:
    kind: str                # 'md' | 'pdf' | 'docx' | 'csv' | 'json' | 'image'
    title: str | None
    sections: list[ParsedSection] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


class Parser:
    """ABC for parsers."""
    def parse(self, path: Path) -> ParsedDocument:
        raise NotImplementedError
