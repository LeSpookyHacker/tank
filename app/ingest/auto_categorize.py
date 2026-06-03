"""Infer a DocumentCategory from a file path and content sniff."""
from __future__ import annotations
from pathlib import Path

_PATH_RULES: list[tuple[str, str]] = [
    # architecture / detections
    ("architect", "architecture"), ("design", "architecture"),
    ("diagram", "architecture"), ("infra", "architecture"),
    ("detection", "architecture"), ("sigma", "architecture"),
    # cmdb
    ("cmdb", "cmdb"), ("inventor", "cmdb"), ("asset", "cmdb"),
    ("iam", "cmdb"), ("cloud", "cmdb"), ("service", "cmdb"),
    # people_process
    ("runbook", "people_process"), ("playbook", "people_process"),
    ("polic", "people_process"), ("compliance", "people_process"),
    ("people", "people_process"), ("org", "people_process"),
    ("postmortem", "people_process"), ("process", "people_process"),
    ("onboard", "people_process"),
]

_EXT_DEFAULTS: dict[str, str] = {
    ".pdf": "architecture",
    ".png": "architecture", ".jpg": "architecture", ".jpeg": "architecture",
    ".mmd": "architecture",
    ".docx": "people_process", ".csv": "cmdb",
}

PARSEABLE_EXTS = {
    ".md", ".markdown", ".mmd", ".pdf", ".docx", ".txt",
    ".png", ".jpg", ".jpeg", ".csv", ".json", ".yml", ".yaml",
}


def suggest_category(path: Path, rel: Path | None = None) -> str:
    """Return best-guess category for *path* using path components + content sniff."""
    check_path = rel or path
    lowered = "/".join(p.lower() for p in check_path.parts)

    for keyword, cat in _PATH_RULES:
        if keyword in lowered:
            return cat

    if path.suffix.lower() in {".json", ".yml", ".yaml"}:
        try:
            snippet = path.read_text(errors="ignore")[:600]
            if '"Version": "2012-10-17"' in snippet or '"Statement"' in snippet:
                return "cmdb"
            if "logsource:" in snippet and "detection:" in snippet:
                return "architecture"
            if '"framework"' in snippet and '"controls"' in snippet:
                return "people_process"
        except Exception:
            pass

    return _EXT_DEFAULTS.get(path.suffix.lower(), "people_process")


def walk_directory(root: Path) -> list[tuple[Path, str]]:
    """Return (path, category) pairs for all parseable files under *root*."""
    results = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(
            part.startswith(".") or part in
            {"__pycache__", "node_modules", ".venv", "dist", "build"}
            for part in rel.parts
        ):
            continue
        if p.suffix.lower() not in PARSEABLE_EXTS:
            continue
        results.append((p, suggest_category(p, rel)))
    return results
