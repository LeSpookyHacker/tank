"""Local sentence-transformer embeddings.

Lazy singleton — the model loads on first call (~80MB download on
first run, then cached in `~/.cache/huggingface/`).

Embeds the *redacted* chunk text only. Originals never leave the
machine.
"""
from __future__ import annotations

from typing import Iterable

_MODEL = None
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _load_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def embed_chunks(texts: Iterable[str]) -> list[list[float]]:
    """Return a list of 384-dim embeddings (one per input)."""
    texts = list(texts)
    if not texts:
        return []
    model = _load_model()
    embeddings = model.encode(
        texts, batch_size=32, convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [row.tolist() for row in embeddings]


def embed_query(text: str) -> list[float]:
    return embed_chunks([text])[0]
