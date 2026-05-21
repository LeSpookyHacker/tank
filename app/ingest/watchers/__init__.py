"""Opt-in continuous-ingestion connectors.

Each watcher implements `scan(watcher_row) -> ScanResult` and the
scheduler calls it at the watcher's cadence.

Watchers ship disabled by default. The user enables them via
Settings → Integrations.
"""
from app.ingest.watchers.folder import FolderWatcher
from app.ingest.watchers.ics import ICSWatcher
from app.ingest.watchers.cve import CVEWatcher
from app.ingest.watchers.github import GitHubWatcher


def dispatch(kind: str):
    return {
        "folder": FolderWatcher,
        "ics_url": ICSWatcher,
        "cve_feed": CVEWatcher,
        "github_repo": GitHubWatcher,
    }.get(kind)
