"""Semantic-ish chunking with overlap.

Target 800 tokens with 120-token overlap, splitting on paragraph >
newline > space boundaries. Token counts via tiktoken (close enough
to Claude's tokenizer for sizing).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_ENC = None


def _enc():
    global _TOKEN_ENC
    if _TOKEN_ENC is None:
        import tiktoken
        _TOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    return _TOKEN_ENC


def count_tokens(text: str) -> int:
    return len(_enc().encode(text))


@dataclass(frozen=True)
class ChunkInput:
    text: str
    section_path: str | None = None
    extra_meta: dict | None = None


@dataclass(frozen=True)
class ChunkOutput:
    ordinal: int
    text: str
    section_path: str | None
    token_count: int


_SPLITTERS = ["\n\n", "\n", ". ", " "]


def split(text: str, *, target_tokens: int = 800,
          overlap_tokens: int = 120,
          section_path: str | None = None) -> list[ChunkOutput]:
    """Split `text` into chunks of ~target_tokens with overlap.

    Returns a list of ChunkOutput. If `text` already fits in a single
    chunk, returns one chunk with ordinal=0.
    """
    if not text.strip():
        return []
    if count_tokens(text) <= target_tokens:
        return [ChunkOutput(
            ordinal=0, text=text, section_path=section_path,
            token_count=count_tokens(text),
        )]

    enc = _enc()
    tokens = enc.encode(text)
    out: list[ChunkOutput] = []
    start = 0
    ordinal = 0
    while start < len(tokens):
        end = min(start + target_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        # Try to snap to a natural boundary near the end.
        chunk_text = _snap_to_boundary(chunk_text)
        out.append(ChunkOutput(
            ordinal=ordinal,
            text=chunk_text,
            section_path=section_path,
            token_count=count_tokens(chunk_text),
        ))
        if end == len(tokens):
            break
        start = max(end - overlap_tokens, start + 1)
        ordinal += 1
    return out


def _snap_to_boundary(text: str) -> str:
    """If the chunk ends mid-sentence, try to back up to the nearest
    sentence/paragraph boundary so the chunk reads cleanly.
    """
    if len(text) < 200:
        return text
    tail_window = text[-400:]
    for splitter in _SPLITTERS:
        idx = tail_window.rfind(splitter)
        if idx > 200:
            return text[:len(text) - len(tail_window) + idx + len(splitter)]
    return text


def split_with_sections(sections: list[ChunkInput], *,
                        target_tokens: int = 800,
                        overlap_tokens: int = 120) -> list[ChunkOutput]:
    """Chunk a list of sections, preserving section_path per chunk."""
    out: list[ChunkOutput] = []
    global_ordinal = 0
    for sec in sections:
        for c in split(sec.text, target_tokens=target_tokens,
                       overlap_tokens=overlap_tokens,
                       section_path=sec.section_path):
            out.append(ChunkOutput(
                ordinal=global_ordinal, text=c.text,
                section_path=c.section_path, token_count=c.token_count,
            ))
            global_ordinal += 1
    return out
