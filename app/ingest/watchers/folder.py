"""Folder watcher: scans a directory for new/changed files, ingests them."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from app.ingest.pipeline import ingest
from app.storage import documents_store

log = logging.getLogger("tank.watchers.folder")


class FolderWatcher:
    def scan(self, watcher: dict) -> dict:
        target = Path(watcher["target"]).expanduser().resolve()
        if not target.is_dir():
            return {"error": f"no such directory: {target}"}
        category = watcher.get("category") or "architecture"
        last_scan = watcher.get("last_scan_at") or 0
        new_count = 0
        ingested: list[str] = []
        for p in sorted(target.rglob("*")):
            # Skip symlinks — they can point outside the watched tree.
            if p.is_symlink() or not p.is_file():
                continue
            # Extra guard: ensure resolved path stays under target root.
            try:
                p.resolve().relative_to(target)
            except ValueError:
                continue
            # Skip hidden + binary-ish files.
            if any(part.startswith(".") for part in p.relative_to(target).parts):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime <= last_scan:
                continue
            try:
                doc_id = ingest(p, category=category)
                ingested.append(doc_id)
                new_count += 1
            except Exception as exc:
                log.warning("folder watcher: failed to ingest %s: %s", p, exc)
        return {
            "ingested_count": new_count,
            "ingested_doc_ids": ingested,
            "scanned_at": time.time(),
        }
