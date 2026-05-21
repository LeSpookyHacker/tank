"""Bulk ingest CLI.

Usage:
    python -m scripts.ingest_cli <path> --category architecture
    python -m scripts.ingest_cli <repo_root> --category code --repo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.ingest.pipeline import ingest, ingest_repo


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=str)
    parser.add_argument("--category", required=True,
                        choices=["architecture", "code", "cmdb", "people_process"])
    parser.add_argument("--repo", action="store_true",
                        help="treat path as a source repo (use the walker)")
    args = parser.parse_args(argv)

    p = Path(args.path).expanduser().resolve()
    if not p.exists():
        print(f"error: no such path: {p}", file=sys.stderr)
        return 2

    if args.repo or (p.is_dir() and not args.repo):
        if not p.is_dir():
            print(f"error: --repo requires a directory; got {p}",
                  file=sys.stderr)
            return 2
        doc_id = ingest_repo(p, category=args.category)
        print(f"ingested repo {p.name} → document_id={doc_id}")
    else:
        doc_id = ingest(p, category=args.category)
        print(f"ingested {p.name} → document_id={doc_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
