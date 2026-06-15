# Security Policy

## Supported versions

Tank is actively maintained. Security fixes are applied to the latest version on `main`.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report security issues privately using one of these channels:

- **GitHub private vulnerability report** (preferred): Use the
  ["Report a vulnerability"](https://github.com/LeSpookyHacker/tank/security/advisories/new)
  button on the Security tab of this repository.
- **Email**: Contact the maintainer directly via the GitHub profile.

### What to include

- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept or minimal repro)
- Any suggested mitigations you have identified

### Response timeline

| Stage | Target |
|---|---|
| Acknowledgement | within 72 hours |
| Triage & severity assessment | within 7 days |
| Patch for critical / high issues | within 14 days |
| Coordinated disclosure | we will notify you before any public disclosure |

### Scope

Tank is a **local-first, single-user application** designed to run on your own machine or
private VM. The relevant attack surface is:

- **Redaction engine** (`app/redact/`) — any bypass that allows plaintext to reach the Anthropic API
- **Ingest pipeline** (`app/ingest/`) — path traversal, SSRF, or arbitrary file reads
- **Web interface** (`app/routers/`, `app/templates/`) — XSS, CSRF, or authentication bypass
- **LLM integration** (`app/claude/`) — prompt injection or output mishandling

Issues in the sample data or documentation that do not affect the running application are
low priority but still welcome.

## Security design

See [`docs/architecture.md`](docs/architecture.md) for Tank's privacy-first architecture
and [`docs/security/`](docs/security/) for past security audit reports.
