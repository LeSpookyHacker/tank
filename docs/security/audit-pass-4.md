# Tank — Security Audit Pass 4

**Date:** 2026-05-29  
**Reviewer:** Claude Opus (adversarial mode)  
**Iteration:** 4 of 4 (fresh full re-audit)  
**Deliverable:** Report + applied fixes, committed to branch

---

## Codebase Map

### Technology Stack
- **Runtime:** Python 3.9+ (FastAPI + uvicorn), SQLite (WAL mode, FK enforced)
- **AI API:** Anthropic Claude Sonnet 4.6 (reasoning) / Haiku (extraction)
- **Embeddings:** sentence-transformers `all-MiniLM-L6-v2` (local, no API)
- **Key libraries:** Pydantic 2, Jinja2, python-multipart, pypdf, python-docx, detect-secrets, pathspec

### Entry Points
| Surface | Description |
|---------|-------------|
| HTTP (FastAPI) | 160+ endpoints across 35 routers; binds `127.0.0.1:8000` by default |
| File upload | `POST /api/ingest/file` (multipart), `POST /api/dfd/start-analysis-image` |
| Local filesystem | `POST /api/ingest/path`, `POST /api/ingest/repo` (local path, home-dir gated) |
| Folder watcher | Continuous scan of a registered local folder |
| ICS watcher | Fetches remote `.ics` calendar URL |
| CVE watcher | Fetches NVD API (hardcoded domain) |
| GitHub watcher / discovery | Fetches `api.github.com` (hardcoded domain) |

### Sensitive Data
Anthropic API key, redaction map (hostnames / emails / cloud IDs in cleartext; secret tokens as SHA-256 hashes), ingested document originals, chat history, entity graph, risk register.

### Trust Boundaries
1. **Untrusted → Ingest pipeline:** User-supplied files / paths / URLs.
2. **Ingest pipeline → Claude API:** Redacted text only (`app/redact/engine.py` chokepoint).
3. **Claude API → KB:** Redacted responses; rehydration is local.
4. **Ingested docs → Chat prompts:** KB chunks labeled as untrusted data (`caching.py` trust header).

---

## Prior Audit History

Three prior adversarial passes have already fixed 34 vulnerabilities. This pass re-confirms each fix holds and audits the entire attack surface from scratch.

| Pass | Key themes | Findings fixed |
|------|-----------|----------------|
| 1 | Auth gate, CSRF, ReDoS, ICS SSRF, prompt-injection delimiting, CSP, HSTS | 11 |
| 2 | DFD redaction bypasses, XSS (`| safe`), path validation, exception leakage | 16 |
| 3 | Redaction bypasses ×7, FTS5 injection, symlink traversal, secret-pattern expansion | 13 |

---

## Re-Confirmed Secure (prior fixes verified intact)

| Area | Verification |
|------|-------------|
| **API-key gate** (`main.py:72-94`) | Optional `TANK_API_KEY`; `secrets.compare_digest`; exempt `/healthz` and `/static/*` only |
| **CSRF on `/api/wipe`** | Requires `X-Confirm: delete-tank` custom header + phrase; `DELETE` endpoints implicitly safe (no permissive CORS) |
| **ICS watcher SSRF** (`ics.py:26-71`) | Full DNS-resolve + RFC-1918/loopback/metadata blocklist + IPv4-mapped IPv6 unwrap |
| **cve_feed watcher SSRF** (`cve.py:46`) | Hardcoded `services.nvd.nist.gov` domain; no user-supplied URL |
| **github_repo watcher SSRF** (`github.py`) | Hardcoded `api.github.com`; user supplies only org/repo name |
| **Discovery SSRF** (`discovery.py`) | Same: hardcoded `api.github.com` |
| **SQL injection** | All queries parameterized; dynamic `UPDATE` column lists allowlisted in `role.py`, `teams_store.py`, `projects_store.py`; FTS5 queries phrase-quoted |
| **Command injection** | No `subprocess`/`os.system`/`eval`/`exec`; repo ingest reads a local path (no `git clone`) |
| **Deserialization** | `yaml.safe_load` in all parsers; no `pickle`, `marshal`, `jsonpickle` |
| **Path traversal (upload)** | `os.path.basename` + tempdir; `ingest/path` restricted to `Path.home()` via `.resolve()` + `os.sep` prefix |
| **Symlink traversal (folder watcher)** | `folder.py` resolves symlinks and confirms resolved path stays under target root |
| **XSS (templates)** | All markdown-rendering templates use `marked` + DOMPurify; `chat.html:39` uses autoescaped `{{ }}` |
| **ReDoS (custom rules)** | `SIGALRM` 1-second deadline at 40/100/200 chars adversarial input |
| **Placeholder format injection** | `_VALID_PLACEHOLDER_FMT` regex restricts to `[PREFIX_{n}]` / `[PREFIX_{n:03d}]` form |
| **Redaction completeness** | Vision/image output redacted post-extraction; entity names redacted in scope blocks for reports, threat models, decisions, tabletops, meeting prep, philosophy, attack mapping, IAM |
| **Randomness** | All IDs via `uuid.uuid4().hex` (cryptographically secure) |
| **DoS bounds** | Upload caps: 100MB (ingest), 20MB (DFD/image), 10MB (ICS); PDF capped 2,000 pages; CSV capped 50,000 rows; entity graph depth/hops bounded |
| **Secrets in repo** | `.env` in `.gitignore`; no committed keys; API key read from env, never logged |

---

## Findings — New (Pass 4)

---

### [MEDIUM] VULN-P4-01: Sensitive-Path Blocklist Gap on One-Off Ingest

**Category:** OWASP A01 – Broken Access Control  
**Severity:** Medium  
**Confidence:** Confirmed  
**Location:** `app/routers/ingest.py` (lines 91–131) — fixed in this pass

**Description:**
`POST /api/ingest/path` and `POST /api/ingest/repo` gated path access to `Path.home()` via an allowlist check, but applied no fine-grained blocklist for sensitive subdirectories. A user (or automation triggering the endpoint when `TANK_API_KEY` is unset) could ingest `~/.ssh/id_rsa`, `~/.aws/credentials`, or `~/.tank/db.sqlite` — exposing private keys, cloud credentials, or Tank's own database.

The folder watcher (`integrations.py:_validate_watcher_target`) had its own inline blocklist (`/etc`, `/proc`, `/sys`, `/dev`, `/root`, `~/.ssh`, `~/.gnupg`), but this guard was not shared with the one-off ingest endpoints.

**Evidence (before fix):**
```python
# ingest.py:91-97
@router.post("/ingest/path")
async def ingest_path(req: IngestPathRequest, ...):
    p = Path(req.path).expanduser().resolve()
    if not any(p == r or str(p).startswith(str(r) + os.sep)
               for r in _ALLOWED_INGEST_ROOTS):
        raise HTTPException(403, "path outside allowed ingest directories")
    # ← no fine-grained sensitive-dir check here
```

**Attack Scenario:**
If `TANK_API_KEY` is unset (default) and the app is network-accessible (bound to `0.0.0.0` or via SSH port-forward), an attacker POSTs `{"path": "~/.aws/credentials", "category": "architecture"}`. The file is ingested into the SQLite KB, chunked, and partially sent to the Anthropic API (after redaction; detect-secrets may catch AWS key patterns, but not all credential formats reliably). Even if redacted, the file content is stored in `chunks.text_original` in plaintext. The attacker then retrieves it via chat or the documents API.

**Fix Applied:**
Created `app/ingest/path_guard.py` — a shared helper `is_blocked_path(p: Path) -> str | None` covering `/etc`, `/proc`, `/sys`, `/dev`, `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.tank`, `~/.config`. Both `ingest_path` and `ingest_repo_endpoint` now call this guard (raising HTTP 403) before queuing the task. `_validate_watcher_target` in `integrations.py` is refactored to use the same helper, eliminating the inline copy.

**References:**  
CWE-22 (Path Traversal), OWASP A01:2021

---

### [LOW] VULN-P4-02: SQL Identifier Injection Risk in `_add_col_safe`

**Category:** OWASP A03 – Injection  
**Severity:** Low  
**Confidence:** Confirmed (currently safe; regression risk)  
**Location:** `app/db.py` (line 651–656) — fixed in this pass

**Description:**
`_add_col_safe(conn, table, col_def)` interpolates `table` directly into `PRAGMA table_info({table})` and `ALTER TABLE {table} ADD COLUMN {col_def}`. All eight current call sites pass hardcoded string literals (`"documents"`, `"projects"`, etc.), so no injection is possible today. However, the function has no input validation — a future caller passing user-supplied or interpolated table names would introduce a SQL injection sink.

**Evidence (before fix):**
```python
def _add_col_safe(conn, table: str, col_def: str) -> None:
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    col_name = col_def.split()[0]
    if col_name not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
```

**Fix Applied:**
Added identifier validation at function entry using a compiled regex `_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")`. Raises `ValueError` for any non-identifier `table` argument, preventing future regression.

**References:**  
CWE-89 (SQL Injection), CWE-20 (Improper Input Validation)

---

### [LOW] VULN-P4-03: Dynamic `UPDATE` Column Names Built from `**kwargs` Without Identifier Validation

**Category:** OWASP A03 – Injection  
**Severity:** Low  
**Confidence:** Confirmed (currently safe; regression risk)  
**Location:** `app/storage/teams_store.py` (line 53–62), `app/storage/projects_store.py` (line 83–93) — fixed in this pass

**Description:**
`update_team(**kwargs)` and `update_project(**kwargs)` build `UPDATE` SET clauses by interpolating dict keys directly into an f-string: `f"{k} = ?"`. The keys are filtered through an allowlist set first, so only known column names pass through today. However, the allowlist is the only safety net — if a key somehow appeared in the allowlist that contained SQL metacharacters (e.g., a typo adding `"name; DROP TABLE teams--"`), it would execute as SQL.

The belt-and-suspenders fix is to add a safe-identifier assertion after allowlist filtering so the invariant is locally enforced rather than depending on the allowlist alone.

**Evidence (before fix):**
```python
def update_team(team_id: str, **kwargs: str) -> None:
    allowed = {"name", "description", "color", "icon", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    set_clause = ", ".join(f"{k} = ?" for k in updates)  # k interpolated
```

**Fix Applied:**
After allowlist filtering, both functions now assert `_SAFE_IDENT.match(k)` for each key, raising `ValueError` on any non-identifier (can only happen if the allowlist itself is corrupted — makes violations impossible to overlook).

**References:**  
CWE-89 (SQL Injection), CWE-693 (Protection Mechanism Failure)

---

## Findings — Documented, Not Auto-Fixed

---

### [MEDIUM] VULN-P4-04: CSP `script-src 'unsafe-inline'` Weakens XSS Defense

**Category:** OWASP A05 – Security Misconfiguration  
**Severity:** Medium  
**Confidence:** Confirmed  
**Location:** `app/main.py` (lines 59–65)

**Description:**
The `Content-Security-Policy` header allows `'unsafe-inline'` in `script-src`:

```python
"script-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com; "
```

This renders the CSP ineffective against XSS: if an attacker can inject any HTML (e.g., via a future `| safe` regression or a stored XSS in a third-party CDN asset), inline scripts will execute.

**Why not auto-fixed:** All templates rely on inline `<script>` blocks and inline event handlers. Removing `'unsafe-inline'` requires a nonce-based or hash-based migration across ~20 templates, touching approximately 500 lines of JavaScript. High breakage risk without a systematic test harness for the full UI. Recommended as a separate, planned effort.

**Recommended Fix:**
1. Audit each inline script in templates; extract to static `.js` files served from `app/static/`.
2. For remaining inline uses, generate a per-request nonce in `_SecurityHeadersMiddleware` and inject it via `request.state.csp_nonce`.
3. Replace `'unsafe-inline'` with `'nonce-{nonce}'` in the CSP.
4. Consider SRI (`integrity=` hashes) for CDN assets.

**References:**  
CWE-79, OWASP A05:2021, [MDN CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)

---

### [LOW] VULN-P4-05: GitHub Token Accepted in POST Body (May Surface in Logs)

**Category:** OWASP A09 – Security Logging & Monitoring Failures  
**Severity:** Low  
**Confidence:** Likely  
**Location:** `app/routers/discovery.py` (line ~73)

**Description:**
`POST /api/discovery/github-scan` accepts a GitHub personal-access token in the JSON request body. The token is only used for the API call (not stored), but it will appear in FastAPI/uvicorn access logs if request-body logging is enabled, and in any HTTP proxy / reverse proxy that logs request bodies.

**Recommended Fix:**
Accept the token via an `Authorization: Bearer <token>` request header or via an environment variable (`TANK_GITHUB_TOKEN`). The watcher already reads from `TANK_GITHUB_TOKEN`; the discovery endpoint should do the same, falling back to the header only if the env var is unset.

**References:**  
CWE-312 (Cleartext Storage of Sensitive Information), CWE-532 (Insertion of Sensitive Information into Log File)

---

### [INFO] VULN-P4-06: Architecture Images Sent to Anthropic API in Cleartext

**Category:** OWASP GenAI LLM06 – Sensitive Information Disclosure  
**Severity:** Informational  
**Confidence:** Confirmed (by design)  
**Location:** `app/ingest/parsers/image.py`, `app/claude/extractor.py` — **UI disclosure applied in this pass**

**Description:**
When a diagram/image is ingested, the raw image bytes are base64-encoded and sent to the Anthropic API for vision-based entity extraction. The extracted text is redacted post-extraction before storage, but the original image (which may contain hostnames, IPs, or internal architecture details) is sent unredacted. This is an inherent limitation of pre-ingestion image processing.

**Fix Applied:**
- `app/templates/ingest.html`: A hidden `#vision-notice` disclosure banner is shown automatically when the user selects one or more PNG/JPG files. Text: *"Images (PNG/JPG) are sent to the Anthropic API in their original form for AI-based text extraction. Internal hostnames, IP addresses, or other sensitive details visible in the image are transmitted before local redaction is applied."*
- `app/templates/dfd.html`: The existing `#upload-image-notice` (already shown when an image is selected for DFD analysis) was updated to include the same privacy language, replacing the previous vague accuracy-only message.
- `app/static/style.css`: Added `.ingest-vision-notice` style matching the `dfd-notice` treatment.

---

### [INFO] VULN-P4-07: Unpinned Dependency Versions

**Category:** OWASP A06 – Vulnerable & Outdated Components  
**Severity:** Informational  
**Confidence:** Confirmed  
**Location:** `requirements.txt`

**Description:**
All dependencies use `>=` lower bounds with no upper pins. This ensures security patches are picked up automatically on re-install but introduces supply-chain drift — a new major version of a dependency could change behavior silently.

No packages had known CVEs as of audit date.

**Recommended Fix:**
For production deployments, generate a lock file: `pip-compile requirements.txt > requirements.lock` and install from the lock file. Keep it refreshed on a scheduled basis.

---

### [INFO] VULN-P4-08: Prompt Injection via Ingested Documents (Mitigated, Residual)

**Category:** OWASP GenAI LLM01 – Prompt Injection  
**Severity:** Informational  
**Confidence:** Possible  
**Location:** `app/claude/caching.py` (lines 42–49)

**Description:**
Maliciously crafted ingested documents could attempt to inject instructions into chat prompts. The `_KB_TRUST_HEADER` explicitly labels retrieved chunks as untrusted data and instructs the model to treat them as data only. This is the appropriate mitigation for the current threat model (single-user, self-ingested documents). It is not a cryptographic guarantee — a sufficiently sophisticated injection may still influence model behavior.

**Recommended Fix:**
No code change needed for current threat model. If Tank is ever extended to ingest documents from third-party or adversarial sources, consider stronger structural delimiting (e.g., XML-tagged blocks) and output validation for tool-use responses.

---

## Session Summary

### Files Reviewed This Pass

**Core:**  
`app/main.py`, `app/config.py`, `app/db.py`, `app/schemas.py`, `app/role.py`

**Redaction:**  
`app/redact/engine.py`, `app/redact/rules.py`, `app/redact/config.py`, `app/redact/secrets.py`, `app/redact/store.py`

**Ingest:**  
`app/ingest/pipeline.py`, `app/ingest/chunker.py`, `app/ingest/embedder.py`, `app/ingest/code_facts.py`, `app/ingest/auto_categorize.py`, `app/ingest/parsers/__init__.py`, `app/ingest/parsers/image.py`, `app/ingest/parsers/pdf.py`, `app/ingest/parsers/docx.py`, `app/ingest/parsers/csv_json.py`, `app/ingest/parsers/markdown.py`, `app/ingest/parsers/sigma.py`, `app/ingest/parsers/iam.py`, `app/ingest/parsers/control_framework.py`, `app/ingest/watchers/__init__.py`, `app/ingest/watchers/ics.py`, `app/ingest/watchers/cve.py`, `app/ingest/watchers/github.py`, `app/ingest/watchers/folder.py`

**KB / Chat:**  
`app/kb/tools.py`, `app/kb/search.py`, `app/kb/relationships.py`, `app/claude/chat.py`, `app/claude/caching.py`, `app/claude/extractor.py`

**Routers:**  
`app/routers/ingest.py`, `app/routers/integrations.py`, `app/routers/chat.py`, `app/routers/settings.py`, `app/routers/discovery.py`, `app/routers/dfd.py`, `app/routers/risks.py`, `app/routers/vulnerabilities.py`, `app/routers/reports.py`, `app/routers/ir_runbooks.py`

**Storage:**  
`app/storage/teams_store.py`, `app/storage/projects_store.py`, `app/storage/organizations_store.py`, `app/storage/policies_store.py`, `app/storage/chunks_store.py`, `app/storage/conversations_store.py`

**New files:**  
`app/ingest/path_guard.py` (created), `tests/test_ingest_path_guard.py` (created)

**Config / Deps:**  
`.env.example`, `requirements.txt`, `scripts/start.sh`

### Finding Count by Severity

| Severity | Count | Fixed this pass |
|----------|-------|-----------------|
| Critical | 0 | — |
| High | 0 | — |
| Medium | 2 | 1 (VULN-P4-01) |
| Low | 3 | 2 (VULN-P4-02, VULN-P4-03) |
| Informational | 3 | 1 (VULN-P4-06 — UI disclosure) |

### Recommended Focus for Next Iteration

1. **CSP nonce migration (VULN-P4-04):** High effort, high security payoff. Plan inline-script extraction + nonce injection as a dedicated sprint.
2. **GitHub token in body (VULN-P4-05):** Low effort; swap to `Authorization: Bearer` header or `TANK_GITHUB_TOKEN` env var.
3. **UI disclosure for vision (VULN-P4-06):** One-line addition to image ingest UI.
4. **Multi-user / RBAC:** Not in current scope, but if Tank ever serves multiple users, project-level access control on documents/reports/conversations/entities is a mandatory addition.

### Open Questions

1. **Is `TANK_API_KEY` documented as required in deployment guides?** The env var is documented in `.env.example` but marked "Recommended" rather than "Required" — clarify if the threat model assumes localhost-only access.
2. **Are there plans to expose Tank behind a reverse proxy?** If so, CORS origin restrictions and the CSP nonce migration should happen before that deployment.
