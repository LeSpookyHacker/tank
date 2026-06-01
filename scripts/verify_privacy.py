"""Privacy assertion helper.

Scans the SQLite DB for any field that *should* have been redacted but
appears in cleartext in places that would have been sent to Claude
(messages.redacted_view, chunks.text_redacted, reports.content_md_redacted).

Run after a full ingest + a chat session. Exit code 0 = pass, 1 = fail.

Usage:
    python -m scripts.verify_privacy [--db PATH] [--fixture-pack]

`--fixture-pack` enables an extra check that the MedScribe-R-Us planted
identifiers (AKIAIOSFODNN7EXAMPLE, api.medscribe.internal, 10.20.30.40,
the Slack/GitHub/Google API keys, and the @medscribe-r-us.fake email
domain) NEVER appear in any redacted field.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


# These should NEVER appear in any *_redacted column. Every needle is a planted
# MedScribe-R-Us identifier that one of the redaction rules is guaranteed to catch
# (AWS-key / Slack / GitHub / Google-API-key patterns, internal hostnames under
# .internal, RFC1918 IPs, and the corporate email domain). Each appears verbatim
# in at least one file under sample_data/seeds/.
MEDSCRIBE_FIXTURE_NEEDLES = [
    # Secrets (rules.py AKIA pattern + secrets.py detect-secrets / extra patterns)
    "AKIAIOSFODNN7EXAMPLE",
    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "xoxb-7700000000-MedScribeFAKEtoken00",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "AIzaSyDmedscribeFAKEvertexkey0123456789",
    # Internal hostnames (.internal → internal_hostname rule)
    "api.medscribe.internal",
    "mongo-prod.medscribe.internal",
    "vertex-proxy.medscribe.internal",
    "auth.medscribe.internal",
    # Private IP (RFC1918)
    "10.20.30.40",
    # Corporate email domain (only ever appears inside email addresses)
    "medscribe-r-us.fake",
]


def scan(db_path: Path, needles: list[str]) -> dict:
    """Return {needle: [(table, column, row_id), ...]} for any hits."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    findings: dict[str, list[tuple[str, str, str]]] = {n: [] for n in needles}

    # Tables/columns that hold redacted-text views.
    targets = [
        ("chunks", "text_redacted", "id"),
        ("messages", "redacted_view", "id"),
        ("messages", "content_json", "id"),
        ("reports", "content_md_redacted", "id"),
        ("nudges", "body", "id"),
        ("nudges", "title", "id"),
        ("journal_entries", "body_redacted", "id"),
        ("notes", "body_redacted", "id"),
    ]
    for table, col, key in targets:
        try:
            rows = conn.execute(
                f"SELECT {key} AS id, {col} AS v FROM {table} "
                f"WHERE {col} IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            text = r["v"] or ""
            for needle in needles:
                if needle in text:
                    findings[needle].append((table, col, r["id"]))
    return findings


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=str,
                   default=os.environ.get("TANK_DB_PATH")
                           or str(Path.home() / ".tank" / "db.sqlite"))
    p.add_argument("--fixture-pack", action="store_true",
                   help="check that MedScribe-R-Us fixture identifiers "
                        "never appear in redacted fields")
    p.add_argument("--also", action="append", default=[],
                   help="additional needle to scan for (repeatable)")
    args = p.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: no DB at {db_path}", file=sys.stderr)
        return 2

    needles = list(args.also)
    if args.fixture_pack:
        needles.extend(MEDSCRIBE_FIXTURE_NEEDLES)
    if not needles:
        print("error: nothing to scan for. Use --fixture-pack or --also <token>.",
              file=sys.stderr)
        return 2

    print(f"scanning {db_path}")
    print(f"needles: {len(needles)}")
    print()

    findings = scan(db_path, needles)
    fail = False
    for needle, hits in findings.items():
        if hits:
            fail = True
            print(f"FAIL  {needle!r} found in {len(hits)} redacted field(s):")
            for table, col, row_id in hits[:5]:
                print(f"  - {table}.{col} (id={row_id})")
            if len(hits) > 5:
                print(f"  - ...and {len(hits) - 5} more")
        else:
            print(f"PASS  {needle!r} — not present in any redacted field")

    print()
    if fail:
        print("PRIVACY ASSERTION FAILED.", file=sys.stderr)
        print("Cleartext that should have been redacted leaked into "
              "fields that get sent to Claude. Stop using Tank for "
              "real data until the redaction engine is fixed.",
              file=sys.stderr)
        return 1
    print("PRIVACY ASSERTION PASSED. No fixture identifiers found in "
          "any redacted field.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
