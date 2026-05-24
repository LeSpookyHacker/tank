"""Bulk-load the Helix Robotics sample data pack into Tank.

Walks `sample_data/` and pushes each artifact through the ingestion
pipeline with the right category. Idempotent: anything already in
`documents` (by sha256) is skipped.

Until Phase 3 (ingestion) lands, `--dry-run` is the only mode that
works — it lists what would be ingested. Once Phase 3 is in, drop
the `--dry-run` flag (or call without it) to actually ingest.

Run with the tank venv activated:
    python -m scripts.load_fixtures              # ingest
    python -m scripts.load_fixtures --dry-run    # just list what we'd do
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "sample_data"


# ---------------- category mapping ----------------

def categorize(path: Path) -> str | None:
    """Map a fixture path to a DocumentCategory, or None to skip."""
    rel = path.relative_to(FIXTURES)
    parts = rel.parts
    top = parts[0] if parts else ""

    if top == "README.md" or rel.name == "README.md" and len(parts) == 1:
        return None      # top-level readme is not ingested
    if rel.name == "company.md":
        return "people_process"
    if top == "architecture":
        return "architecture"
    if top == "repos":
        return None      # repos are handled at the directory level (see plan_repo_ingest)
    if top == "cmdb":
        return "cmdb"
    if top in {"people", "policies", "runbooks", "postmortems", "seeds"}:
        return "people_process"
    if top == "detections":
        return "architecture"
    if top == "iam":
        return "cmdb"
    if top == "compliance":
        return "people_process"
    return None


# ---------------- planning ----------------

def plan_files(fixtures_root: Path) -> list[tuple[Path, str]]:
    """Return (path, category) pairs for individual files we'd ingest."""
    plan: list[tuple[Path, str]] = []
    for path in sorted(fixtures_root.rglob("*")):
        if path.is_dir():
            continue
        # Skip files inside repos/ — repos are ingested as a whole, not
        # file-by-file.
        try:
            rel = path.relative_to(fixtures_root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "repos":
            continue
        # Skip emacs/IDE backups + hidden files.
        if any(p.startswith(".") for p in rel.parts):
            continue
        # Skip the .docx/.pdf/.png markdown twins until generated.
        if path.suffix in {".md.bak"}:
            continue
        cat = categorize(path)
        if cat is None:
            continue
        plan.append((path, cat))
    return plan


def plan_repos(fixtures_root: Path) -> list[Path]:
    """Return the list of repo roots under sample_data/repos/."""
    repos_root = fixtures_root / "repos"
    if not repos_root.exists():
        return []
    return sorted(p for p in repos_root.iterdir() if p.is_dir())


# ---------------- helpers ----------------

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_repo(repo_root: Path) -> str:
    """Aggregate sha256 over a repo's file tree.

    Used to detect "this repo has not changed since last ingest" cheaply,
    without re-walking via Tank's ingestion pipeline. Same shape as the
    per-file sha256 used elsewhere, so we can store both kinds in
    `documents.sha256`.
    """
    h = hashlib.sha256()
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        # Skip Git internals + .venv + node_modules just like the real
        # repo walker would.
        rel = path.relative_to(repo_root)
        if any(p in {".git", ".venv", "node_modules", "__pycache__"}
               for p in rel.parts):
            continue
        h.update(str(rel).encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_of_file(path).encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


# ---------------- dry-run output ----------------

def print_plan(files: list[tuple[Path, str]], repos: list[Path]) -> None:
    print("=" * 72)
    print(f"Fixture plan from {FIXTURES.relative_to(ROOT)}/")
    print("=" * 72)
    print()
    print(f"{'CATEGORY':<16}  {'SHA256 PREFIX':<14}  {'SIZE':>8}  PATH")
    print(f"{'-' * 16}  {'-' * 14}  {'-' * 8}  {'-' * 30}")
    for path, cat in files:
        sha = sha256_of_file(path)[:12]
        size = path.stat().st_size
        rel = path.relative_to(ROOT)
        print(f"{cat:<16}  {sha:<14}  {size:>8}  {rel}")

    if repos:
        print()
        print("Repos (ingested whole, code-facts summary only):")
        for repo in repos:
            sha = sha256_of_repo(repo)[:12]
            n_files = sum(1 for p in repo.rglob("*") if p.is_file())
            rel = repo.relative_to(ROOT)
            print(f"{'code':<16}  {sha:<14}  {n_files:>5}fl  {rel}")

    print()
    print(f"Total files: {len(files)}; total repos: {len(repos)}")
    print()


# ---------------- ingestion (Phase 3+) ----------------

def ingest_file(path: Path, category: str) -> tuple[str, str]:
    """Call into Tank's ingestion pipeline. Returns (status, message)."""
    try:
        from app.ingest.pipeline import ingest as _ingest
    except ImportError:
        return ("not-yet-built",
                "app.ingest.pipeline not present; run --dry-run for now")
    doc_id = _ingest(path, category=category)
    return ("ok", f"document_id={doc_id}")


def ingest_repo(repo_root: Path) -> tuple[str, str]:
    """Call into Tank's repo walker. Returns (status, message)."""
    try:
        from app.ingest.pipeline import ingest_repo as _ingest_repo
    except ImportError:
        return ("not-yet-built",
                "app.ingest.pipeline.ingest_repo not present yet")
    doc_id = _ingest_repo(repo_root)
    return ("ok", f"document_id={doc_id}")


# ---------------- main ----------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan, don't ingest")
    parser.add_argument("--json", action="store_true",
                        help="emit the plan as JSON (implies --dry-run)")
    args = parser.parse_args(argv)

    files = plan_files(FIXTURES)
    repos = plan_repos(FIXTURES)

    if args.json:
        out = {
            "files": [
                {"path": str(p.relative_to(ROOT)),
                 "category": cat,
                 "sha256": sha256_of_file(p)}
                for p, cat in files
            ],
            "repos": [
                {"path": str(r.relative_to(ROOT)),
                 "sha256": sha256_of_repo(r)}
                for r in repos
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.dry_run:
        print_plan(files, repos)
        return 0

    # Real ingest — requires Phase 3+ to be present.
    try:
        from app.ingest.pipeline import ingest as _probe  # noqa: F401
    except ImportError:
        print("Tank's ingestion pipeline (app/ingest/pipeline.py) is not "
              "yet built. Run with --dry-run to see the plan, and re-run "
              "without --dry-run once Phase 3 is in.", file=sys.stderr)
        return 2

    n_ok = 0
    n_skip = 0
    n_fail = 0
    for path, cat in files:
        status, msg = ingest_file(path, cat)
        marker = {"ok": "✓", "skipped": "·"}.get(status, "✗")
        rel = path.relative_to(ROOT)
        print(f"  {marker} {rel}  ({cat})  {msg}")
        n_ok += int(status == "ok")
        n_skip += int(status == "skipped")
        n_fail += int(status not in {"ok", "skipped"})

    for repo in repos:
        status, msg = ingest_repo(repo)
        marker = {"ok": "✓", "skipped": "·"}.get(status, "✗")
        rel = repo.relative_to(ROOT)
        print(f"  {marker} {rel}/  (code)  {msg}")
        n_ok += int(status == "ok")
        n_skip += int(status == "skipped")
        n_fail += int(status not in {"ok", "skipped"})

    print()
    print(f"ingested ok: {n_ok}    skipped: {n_skip}    failed: {n_fail}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
