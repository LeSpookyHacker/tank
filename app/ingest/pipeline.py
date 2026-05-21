"""Ingest orchestration: parse → chunk → redact → embed → extract → store.

Two entrypoints:
    ingest(path, category)        # single file
    ingest_repo(repo_root)        # walks a source repo, summarizes,
                                  # then ingests the summary as a doc
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.ingest.chunker import ChunkInput, split_with_sections
from app.ingest.code_facts import render_summary_text, summarize
from app.ingest.embedder import embed_chunks
from app.ingest.parsers import dispatch
from app.ingest.parsers._base import ParsedDocument
from app.redact.engine import apply_redactions
from app.storage import (
    chunks_store,
    documents_store,
    entities_store,
    relationships_store,
)

log = logging.getLogger("tank.ingest")


# ---------------- helpers ----------------

def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _sha256_repo(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in {".git", ".venv", "node_modules", "__pycache__"}
               for part in rel.parts):
            continue
        h.update(str(rel).encode("utf-8"))
        h.update(b"\0")
        try:
            ph, _ = _sha256_file(p)
        except OSError:
            continue
        h.update(ph.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


# ---------------- single-file ingest ----------------

def ingest(path: str | Path, *, category: str,
           kind_override: str | None = None) -> str:
    """Ingest one file. Returns the document_id (existing or new)."""
    path = Path(path).resolve()
    sha, size = _sha256_file(path)
    existing = documents_store.find_by_sha256(sha)
    if existing:
        log.info("ingest dedup: %s already at %s", path.name, existing["id"])
        return existing["id"]

    parsed = dispatch(path).parse(path)
    doc_id = documents_store.insert_document(
        source_path=str(path),
        kind=kind_override or parsed.kind,
        title=parsed.title,
        sha256=sha,
        size_bytes=size,
        category=category,
        meta=parsed.meta,
    )
    documents_store.update_status(doc_id, "parsing")
    try:
        _process_parsed(doc_id, parsed)
        documents_store.update_status(doc_id, "ready")
    except Exception as exc:
        log.exception("ingest failed for %s", path)
        documents_store.update_status(doc_id, "error",
                                      error_message=str(exc))
        raise
    return doc_id


# ---------------- repo ingest ----------------

def ingest_repo(root: str | Path, *,
                category: str = "code") -> str:
    """Walk a source repo, build a structured summary, ingest the
    summary as one document. No raw code is ever sent to Claude.
    """
    root = Path(root).resolve()
    sha = _sha256_repo(root)
    existing = documents_store.find_by_sha256(sha)
    if existing:
        log.info("ingest_repo dedup: %s already at %s",
                 root.name, existing["id"])
        return existing["id"]

    summary = summarize(root)
    text = render_summary_text(summary)
    # Synthesize a ParsedDocument so the same downstream path works.
    from app.ingest.parsers._base import ParsedDocument, ParsedSection
    parsed = ParsedDocument(
        kind="repo", title=summary.name,
        sections=[ParsedSection(section_path="summary", text=text)],
        meta={
            "languages": summary.languages,
            "manifests": list(summary.manifests.keys()),
            "ci_workflows": summary.ci_workflows,
            "auth_hits": summary.auth_hits,
            "secret_handling_hits": summary.secret_handling_hits,
            "file_count": summary.file_count,
        },
    )
    doc_id = documents_store.insert_document(
        source_path=str(root),
        kind="repo",
        title=summary.name,
        sha256=sha,
        size_bytes=len(text.encode("utf-8")),
        category=category,
        meta=parsed.meta,
    )
    documents_store.update_status(doc_id, "parsing")
    try:
        _process_parsed(doc_id, parsed, extract_kind="repo")
        documents_store.update_status(doc_id, "ready")
    except Exception as exc:
        log.exception("ingest_repo failed for %s", root)
        documents_store.update_status(doc_id, "error",
                                      error_message=str(exc))
        raise
    return doc_id


# ---------------- core processing ----------------

def _process_parsed(doc_id: str, parsed: ParsedDocument,
                    extract_kind: str = "default") -> None:
    # 1. Chunk
    inputs = [ChunkInput(text=s.text, section_path=s.section_path)
              for s in parsed.sections if s.text.strip()]
    chunks = split_with_sections(inputs)
    if not chunks:
        log.info("ingest %s: no chunks after parse (empty content?)", doc_id)
        return

    # 2. Redact every chunk before it touches anything else.
    redacted_pairs = [(c, apply_redactions(c.text)) for c in chunks]

    # 3. Persist chunks (text_original + text_redacted both stored;
    #    text_original never leaves the DB).
    chunk_dicts = []
    for c, red in redacted_pairs:
        chunk_dicts.append({
            "ordinal": c.ordinal,
            "text_original": c.text,
            "text_redacted": red.redacted_text,
            "token_count": c.token_count,
            "section_path": c.section_path,
            "meta": {},
        })
    chunk_ids = chunks_store.bulk_insert_chunks(
        document_id=doc_id, chunks=chunk_dicts,
    )

    # 4. Embed the redacted chunks (local model, no remote call).
    try:
        embeddings = embed_chunks([d["text_redacted"] for d in chunk_dicts])
        chunks_store.write_vec(chunk_ids, embeddings)
    except Exception as exc:
        log.warning("embedding failed: %s (FTS-only retrieval still works)", exc)

    documents_store.update_status(doc_id, "extracting")

    # 5. Extract entities + edges via Claude. Imported lazily so that
    #    parsing works in tests without an API key.
    from app.claude.extractor import extract_entities_for_doc
    extract_entities_for_doc(doc_id, chunk_dicts, chunk_ids,
                             kind=extract_kind, parsed_meta=parsed.meta)
