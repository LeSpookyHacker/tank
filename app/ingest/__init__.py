"""Document ingestion: parse → chunk → redact → embed → extract → store.

Public entrypoints:
    from app.ingest import ingest, ingest_repo
"""
from app.ingest.pipeline import ingest, ingest_repo

__all__ = ["ingest", "ingest_repo"]
