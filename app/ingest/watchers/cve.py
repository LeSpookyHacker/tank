"""CVE feed watcher: opt-in NVD subscription filtered by deps Tank knows about.

Phase 11 ships the scaffold; a full NVD implementation requires API
credentials + careful query filtering. For v1, this is a stub that
demonstrates the contract; the user enables it from Settings and
provides an API key via `TANK_NVD_API_KEY` env var if they want to
use it.
"""
from __future__ import annotations

import logging
import os
import time
import urllib.request
import urllib.parse
import json

from app.storage import nudges_store

log = logging.getLogger("tank.watchers.cve")


class CVEWatcher:
    def scan(self, watcher: dict) -> dict:
        api_key = os.environ.get("TANK_NVD_API_KEY", "").strip()
        if not api_key:
            return {"skipped": "TANK_NVD_API_KEY not set"}

        # Watcher.config_json holds a list of package names to filter on
        # (collected from ingested manifests in Phase 5).
        try:
            cfg = json.loads(watcher.get("config_json") or "{}")
        except Exception:
            cfg = {}
        deps: list[str] = cfg.get("dependencies", [])
        if not deps:
            return {"skipped": "no dependencies in watcher config"}

        # NVD 2.0 query (simplified — fetch last 24h of CRITICAL CVEs).
        since = time.strftime("%Y-%m-%dT00:00:00.000",
                              time.gmtime(time.time() - 86400))
        params = urllib.parse.urlencode({
            "pubStartDate": since,
            "cvssV3Severity": "CRITICAL",
        })
        url = ("https://services.nvd.nist.gov/rest/json/cves/2.0?"
               + params)
        req = urllib.request.Request(url, headers={"apiKey": api_key})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"error": str(exc)}

        new_nudges = 0
        for cve in (data.get("vulnerabilities") or [])[:25]:
            cve_id = cve.get("cve", {}).get("id", "?")
            descs = cve.get("cve", {}).get("descriptions", [])
            desc_text = next(
                (d["value"] for d in descs if d.get("lang") == "en"),
                "",
            )
            lower = desc_text.lower()
            matched = [d for d in deps if d.lower() in lower]
            if not matched:
                continue
            nudges_store.insert(
                kind="dependency_cve",
                title=f"Critical CVE may affect {matched[0]}: {cve_id}",
                body=desc_text[:600],
                payload={"cve_id": cve_id, "matched_deps": matched},
                priority=80,
            )
            new_nudges += 1
        return {"scanned_at": time.time(), "new_nudges": new_nudges}
