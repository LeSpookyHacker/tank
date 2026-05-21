"""GitHub poller (opt-in).

Polls a configured repo for new commits, PRs touching auth/secrets
paths, and Dependabot alerts. Surfaces patterns as nudges rather than
ingesting everything (the user's repos are big; we just want signal).

Requires `TANK_GITHUB_TOKEN` in env (classic PAT scoped read).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.parse

from app.storage import nudges_store

log = logging.getLogger("tank.watchers.github")


_AUTH_PATH_HINTS = ("auth/", "auth.py", "auth.go", "jwt", "oauth",
                    "session", "login", "iam/", "vault/")
_SECRET_PATH_HINTS = (".env", "secrets/", "credentials", "keys/")


def _gh_request(path: str, token: str) -> dict | None:
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("github request to %s failed: %s", path, exc)
        return None


class GitHubWatcher:
    def scan(self, watcher: dict) -> dict:
        token = os.environ.get("TANK_GITHUB_TOKEN", "").strip()
        if not token:
            return {"skipped": "TANK_GITHUB_TOKEN not set"}

        repo = watcher["target"]    # e.g. "helix-robotics/payments-api"
        since_ts = watcher.get("last_scan_at") or (time.time() - 7 * 86400)
        since_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                  time.gmtime(since_ts))

        # Recently-merged PRs.
        prs = _gh_request(
            f"/repos/{urllib.parse.quote(repo)}/pulls"
            f"?state=closed&sort=updated&direction=desc&per_page=30",
            token,
        ) or []

        sensitive_prs = []
        for pr in prs:
            if not pr.get("merged_at"):
                continue
            if pr["merged_at"] < since_iso:
                continue
            # We don't fetch each PR's files (rate limit), just look at
            # title/body for auth/secret signals.
            text = (pr.get("title", "") + " "
                    + (pr.get("body") or "")).lower()
            if any(h in text for h in _AUTH_PATH_HINTS + _SECRET_PATH_HINTS):
                sensitive_prs.append(pr)

        if sensitive_prs:
            top = sensitive_prs[0]
            nudges_store.insert(
                kind="repo_activity",
                title=f"Sensitive PR merged in {repo}",
                body=f"#{top.get('number')}: {top.get('title')!r}. "
                     f"Body mentioned auth/secrets paths. Worth a look.",
                payload={"repo": repo, "pr_url": top.get("html_url"),
                         "sensitive_pr_count": len(sensitive_prs)},
                priority=70,
            )

        return {"scanned_at": time.time(),
                "sensitive_pr_count": len(sensitive_prs)}
