"""Walk a source-code repo and produce a structured summary.

No raw code is sent to Claude — only the summary + READMEs. This is
how Tank keeps source confidential while still extracting entities.

Detected facts:
- Languages by line count
- Dependency manifests (package.json, pyproject.toml, go.mod, etc.)
- Dockerfile (base image, exposed ports, USER directive)
- CI workflow files
- Auth-related grep hits
- Secrets-handling grep hits
- README + docs/ + ARCHITECTURE.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_EXT_LANG = {
    ".py": "Python", ".pyi": "Python",
    ".go": "Go",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".c": "C", ".h": "C",
    ".sh": "Shell",
    ".swift": "Swift",
}

_MANIFEST_FILES = {
    "requirements.txt", "pyproject.toml", "Pipfile", "setup.py",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.mod", "go.sum",
    "Cargo.toml", "Cargo.lock",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "Gemfile.lock",
    "*.csproj",
}

_AUTH_GREPS = (
    "passport", "okta", "auth0", "oauth", "jwt", "saml", "cognito",
    "iam", "assume_role", "scim", "oidc",
)
_SECRET_HANDLING_GREPS = (
    "aws-sdk", "secretsmanager", "vault", "parameter store",
    "dotenv", "kms", "ssm", "azure-keyvault",
)

_IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "target", ".idea", ".vscode",
}
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf", ".zip", ".gz", ".tar", ".7z",
    ".so", ".dylib", ".dll", ".class", ".jar",
    ".woff", ".woff2", ".ttf", ".otf",
    ".mp3", ".mp4", ".wav",
}
_MAX_FILE_BYTES = 1_000_000


@dataclass
class RepoSummary:
    name: str
    root: str
    languages: dict[str, int] = field(default_factory=dict)
    manifests: dict[str, str] = field(default_factory=dict)
    dockerfile: dict | None = None
    ci_workflows: list[str] = field(default_factory=list)
    auth_hits: list[str] = field(default_factory=list)
    secret_handling_hits: list[str] = field(default_factory=list)
    readme: str | None = None
    architecture_doc: str | None = None
    codeowners: str | None = None
    file_count: int = 0
    skipped: int = 0


def _load_gitignore(root: Path):
    try:
        import pathspec
    except ImportError:
        return None
    gi = root / ".gitignore"
    if not gi.exists():
        return None
    lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _walk_files(root: Path):
    spec = _load_gitignore(root)
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in _IGNORE_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() in _BINARY_EXTS:
            continue
        if spec and spec.match_file(str(rel)):
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield p, rel


def _parse_dockerfile(text: str) -> dict:
    out: dict = {}
    for line in text.splitlines():
        s = line.strip()
        if s.upper().startswith("FROM "):
            out.setdefault("base_images", []).append(s.split(None, 1)[1])
        elif s.upper().startswith("EXPOSE "):
            out.setdefault("exposed_ports", []).extend(s.split()[1:])
        elif s.upper().startswith("USER "):
            out["user"] = s.split(None, 1)[1]
    return out


def summarize(root: Path) -> RepoSummary:
    summary = RepoSummary(name=root.name, root=str(root))
    for p, rel in _walk_files(root):
        summary.file_count += 1
        name = p.name
        ext = p.suffix.lower()

        # Language LOC.
        if ext in _EXT_LANG:
            try:
                loc = sum(1 for _ in p.open("r", encoding="utf-8",
                                            errors="replace"))
            except OSError:
                loc = 0
            lang = _EXT_LANG[ext]
            summary.languages[lang] = summary.languages.get(lang, 0) + loc

        # Manifests.
        for mf in _MANIFEST_FILES:
            if mf.startswith("*."):
                if ext == mf[1:]:
                    summary.manifests[str(rel)] = _safe_read(p, 8_000)
                    break
            elif name == mf:
                summary.manifests[str(rel)] = _safe_read(p, 8_000)
                break

        # Dockerfile (any name starting with Dockerfile).
        if name == "Dockerfile" or name.startswith("Dockerfile."):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                summary.dockerfile = _parse_dockerfile(text)
                summary.dockerfile["path"] = str(rel)
            except OSError:
                pass

        # CI workflows.
        rel_str = str(rel).replace("\\", "/")
        if (rel_str.startswith(".github/workflows/")
                or rel_str.endswith("gitlab-ci.yml")
                or rel_str.endswith("Jenkinsfile")
                or rel_str.endswith("buildkite.yml")
                or rel_str.endswith("buildspec.yml")):
            summary.ci_workflows.append(rel_str)

        # CODEOWNERS.
        if name == "CODEOWNERS":
            summary.codeowners = _safe_read(p, 4_000)

        # README / ARCHITECTURE.
        if name.lower() in {"readme.md", "readme.rst", "readme.txt"} and \
                summary.readme is None and len(rel.parts) <= 2:
            summary.readme = _safe_read(p, 30_000)
        if name.lower() == "architecture.md" and summary.architecture_doc is None:
            summary.architecture_doc = _safe_read(p, 30_000)

        # Auth / secrets greps (text files only).
        if ext in _EXT_LANG or ext in {".yaml", ".yml", ".tf", ".json"}:
            try:
                text = p.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            for needle in _AUTH_GREPS:
                if needle in text and rel_str not in summary.auth_hits:
                    summary.auth_hits.append(f"{needle}:{rel_str}")
                    break
            for needle in _SECRET_HANDLING_GREPS:
                if needle in text and rel_str not in summary.secret_handling_hits:
                    summary.secret_handling_hits.append(f"{needle}:{rel_str}")
                    break

    return summary


def _safe_read(p: Path, max_chars: int) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:max_chars]


def render_summary_text(s: RepoSummary) -> str:
    """Turn a RepoSummary into prose Tank can chunk + retrieve.

    This text is what gets sent to Claude during entity extraction
    (along with the README); no raw source code is included.
    """
    lines: list[str] = []
    lines.append(f"# Repository: {s.name}")
    lines.append("")
    lines.append(f"Total files scanned: {s.file_count}")
    lines.append("")

    if s.languages:
        lines.append("## Languages (by line count)")
        for lang, loc in sorted(s.languages.items(),
                                key=lambda kv: kv[1], reverse=True):
            lines.append(f"- {lang}: {loc} lines")
        lines.append("")

    if s.manifests:
        lines.append("## Dependency manifests")
        for path, _content in s.manifests.items():
            lines.append(f"- {path}")
        lines.append("")
        # Embed the contents of common manifests (small + textual).
        for path, content in s.manifests.items():
            lines.append(f"### {path}")
            lines.append("```")
            lines.append(content[:2000])
            lines.append("```")
            lines.append("")

    if s.dockerfile:
        lines.append("## Dockerfile")
        lines.append(f"- path: {s.dockerfile.get('path')}")
        for k in ("base_images", "exposed_ports", "user"):
            if k in s.dockerfile:
                lines.append(f"- {k}: {s.dockerfile[k]}")
        lines.append("")

    if s.ci_workflows:
        lines.append("## CI workflows")
        for w in s.ci_workflows:
            lines.append(f"- {w}")
        lines.append("")

    if s.auth_hits:
        lines.append("## Auth-related hits")
        for h in s.auth_hits:
            lines.append(f"- {h}")
        lines.append("")

    if s.secret_handling_hits:
        lines.append("## Secrets-handling hits")
        for h in s.secret_handling_hits:
            lines.append(f"- {h}")
        lines.append("")

    if s.codeowners:
        lines.append("## CODEOWNERS")
        lines.append("```")
        lines.append(s.codeowners)
        lines.append("```")
        lines.append("")

    if s.readme:
        lines.append("## README")
        lines.append(s.readme[:8000])
        lines.append("")

    if s.architecture_doc:
        lines.append("## ARCHITECTURE.md")
        lines.append(s.architecture_doc[:8000])
        lines.append("")

    return "\n".join(lines)
