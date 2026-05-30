"""Bulk ingest orchestration — the "chuck-it-at-Tank" front door.

Turns a mixed bag of dropped/pointed paths (loose files, folders, and
git repositories) into an ordered list of work items the existing
pipeline can run:

  - A git repo (a dir with ``.git`` or a root build manifest) becomes a
    single ``repo`` item, summarized via ``code_facts`` — never walked
    file-by-file, never sending raw source to Claude.
  - Everything else becomes a ``file`` item, auto-categorized via
    ``suggest_category``.

When a pointed folder *contains* repos, those repos are detected and
pulled out as ``repo`` items; the remaining loose files are swept in
with repo subtrees pruned, so repo source never leaks into document
ingest.

Orchestration only: every file still flows through the unchanged
pipeline (parse -> redact -> embed -> extract), so the privacy contract
is untouched.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.ingest.auto_categorize import PARSEABLE_EXTS, suggest_category

# A directory is treated as a repo if it has a ``.git`` dir or one of these
# build manifests at its root.
_REPO_MANIFESTS = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Gemfile",
}

# Directory names never descended into during the loose-file sweep.
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}


def is_repo(path: Path) -> bool:
    """True if *path* looks like a source repository root."""
    if not path.is_dir():
        return False
    if (path / ".git").exists():
        return True
    return any((path / m).is_file() for m in _REPO_MANIFESTS)


@dataclass
class WorkItem:
    kind: str        # "repo" | "file"
    path: Path
    category: str    # "code" for repos; suggested category for files

    def rel_label(self, base: Path | None = None) -> str:
        if base is not None:
            try:
                return str(self.path.relative_to(base))
            except ValueError:
                pass
        return self.path.name


def plan_bulk(paths: list[str | Path]) -> list[WorkItem]:
    """Expand mixed input paths into an ordered, de-duplicated work list."""
    items: list[WorkItem] = []
    seen: set[Path] = set()

    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            continue
        if p.is_file():
            _add_file(items, seen, p, p.parent)
        elif is_repo(p):
            _add_repo(items, seen, p)
        elif p.is_dir():
            _expand_dir(items, seen, p)

    return items


def _add_repo(items: list[WorkItem], seen: set[Path], path: Path) -> None:
    if path in seen:
        return
    seen.add(path)
    items.append(WorkItem(kind="repo", path=path, category="code"))


def _add_file(items: list[WorkItem], seen: set[Path],
              path: Path, rel_root: Path) -> None:
    if path in seen:
        return
    if path.suffix.lower() not in PARSEABLE_EXTS:
        return
    seen.add(path)
    try:
        rel = path.relative_to(rel_root)
    except ValueError:
        rel = Path(path.name)
    items.append(WorkItem(kind="file", path=path,
                          category=suggest_category(path, rel)))


def _expand_dir(items: list[WorkItem], seen: set[Path], root: Path) -> None:
    """Walk *root* top-down, pulling nested repos out as repo items and
    sweeping the remaining loose files. Repo subtrees are pruned so their
    source is never ingested as documents."""
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)

        # Prune hidden + junk directories before descending.
        dirnames[:] = [dn for dn in dirnames
                       if not dn.startswith(".") and dn not in _SKIP_DIRS]

        # A nested repo: record it and stop descending into it.
        if d != root and is_repo(d):
            _add_repo(items, seen, d)
            dirnames[:] = []
            continue

        for fn in sorted(filenames):
            _add_file(items, seen, d / fn, root)
