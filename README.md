# Tank

<p align="center"><img width="400" height="250" alt="tank" src="https://github.com/user-attachments/assets/ac7cc97d-2d5b-4ede-b795-7d506c2e5267"/></p>

> Your security-engineering operator. Like Tank in *The Matrix* —
> sees the whole map, feeds you context, never lies about what it doesn't know.

A local-first onboarding **and** daily-companion partner for new Sr/Staff/Manager
security engineers. You point it at your new employer's docs, code, CMDB, and
people info. It builds a typed knowledge graph, redacts sensitive identifiers
locally, and uses Claude to help you map the threat landscape, surface gaps,
prepare for meetings, author postmortems and design reviews, run tabletops,
track decisions, maintain a risk register, generate incident-response runbooks,
capture lessons, and stay sharp across your tenure.

> 📖 **Full documentation lives in [docs/](docs/)** — installation
> walkthroughs, architecture deep-dives, per-feature references, FAQ,
> and troubleshooting.

---

## What this is

The first 30/60/90 days of a new security role are dominated by reading docs,
mapping services, identifying owners, and building a mental model of where the
risk lives. Tank shortcuts that — and then **keeps earning its keep** for the
rest of your tenure. You feed it what you're given (architecture PDFs, repo
paths, CMDB exports, org-chart screenshots, runbooks, postmortems, Sigma
detection rules, IAM policies, control frameworks) and it produces:

- Structured recon reports you can re-run weekly — rendered as Markdown with PDF and download export.
- **Living, versioned threat models** that detect when architecture drifts
  and prompt regeneration.
- A **decisions log** with kinds (design choice, accepted risk, deferred fix,
  security invariant), expiry tracking, and reaffirmation flows.
- Authoring scaffolds for **design reviews**, **postmortems**, and
  **tabletop exercises** — all extracting lessons into a searchable DB.
- **DFD threat modeling** — paste or upload a Data Flow Diagram; Tank runs
  STRIDE analysis, annotates the diagram with severity colors, and generates
  a remediation table. Incomplete diagrams can be improved using KB context.
- An **ATT&CK coverage map** + **compliance evidence collection** +
  **IAM policy translator** + **attack-surface ledger** over your ingested
  data.
- A **risk register** (`/risks`) — formal inherent/residual scoring (1-5 L×I),
  treatment strategies (mitigate / accept / transfer / avoid), Sonnet KB-grounded
  assessment, 90-day review scheduling, and `risk_review_due` nudge.
- A **security program dashboard** (`/security-program`) — instant-load page
  aggregating all of Tank's data into 6 KPI domains; on-demand executive brief
  (green / yellow / red health indicator); weekly 12-week trend snapshots.
- **IR runbooks** (`/ir-runbooks`) — per-service, per-scenario 5-phase
  incident-response playbooks (Detect / Contain / Eradicate / Recover / Comms)
  grounded in your KB; integrated with tabletops and postmortems.
- A **personal ownership dashboard** with per-entity risk scoring.
- A curated **security philosophy doc** Tank evolves with you.

**The privacy headline:** Tank runs entirely on your machine. Internal
hostnames, emails, RFC1918 IPs, AWS account IDs, ARNs, GCP projects, Azure
subscriptions, and secrets are redacted on your host *before* any Claude API
call. A SQLite redaction map keeps the mapping local so responses can be
rehydrated for display. Secrets are one-way hashed — Tank cannot rehydrate
them even if asked.

---

## What it does (long form)

### Ingestion + knowledge graph

- Parses architecture docs (PDF/DOCX/MD), source repos (summary only — **no
  raw code ever sent to Claude**), CMDB/asset CSVs, org charts, runbooks,
  postmortems, Sigma detection rules, AWS/K8s/GCP IAM policies, and control
  framework JSON.
- Builds a typed graph of 14 entity kinds linked by 9 relationship kinds.
  Every fact carries a provenance badge: `source`, `inferred`, `claim`, or
  `user`.

### Chat over the KB

- **Persistent side panel** on every page — always accessible without leaving
  your current view, collapsible to a pill, resizable by dragging the left
  edge, conversation preserved across navigation. Full-screen chat available
  at `/chat` for focused sessions.
- SSE-streamed chat with 15 tools (search KB, get entity, list relationships,
  find control gaps, get threat model, find decisions, find detections,
  find IAM risks, search lessons, get risk register, find IR runbooks, …).
- Citations on every reply; click to source chunks.
- **Tenure-aware lens** — Map / Prioritize / Execute / Maintain — shifts
  framing automatically over time.
- **Project-scoped chat** — conversations started within a project automatically
  include that project's notes in the system prompt. The global side panel never
  injects project notes.

### Reports (11 kinds)

`threat_landscape`, `cross_service_gaps`, `plan_30_60_90`, `stakeholder_map`,
`questions_for_team`, `control_matrix`, `oncall_handoff`,
`weekly_security_digest`, `attack_mapping`, `iam_audit`, `risk_register`.
Subscribe any of them on a daily/weekly/monthly cadence; diffs against the
prior run land in your morning digest.

### Workstream artifacts (Phase 13)

- **Design reviews** — freewrite intake → Sonnet-seeded checklist →
  approval → auto-spawns linked decisions.
- **Postmortems** — freewrite → drafted structured fields → publish creates
  followups + extracts lessons.
- **Tabletops** — pick service + threat → 1-paragraph scenario + 4-6 timed
  injects + facilitation + rubric → capture lessons.

### Coverage + visibility (Phase 14)

- **Detection coverage map** — Sigma rules × ATT&CK techniques × services.
- **ATT&CK mapping report** — every threat in every TM → tactic + technique.
- **IAM policy translator** — plain-English explanations + risk callouts
  for AWS / K8s RBAC / GCP IAM.
- **Compliance evidence collection** — ingest a control framework; Tank
  finds matching evidence in the KB; surfaces gaps.
- **Attack-surface ledger** — weekly Endpoint snapshot + diff vs prior.

### DFD Threat Modeling

A three-stage pipeline from diagram input to interactive threat workspace.
Access via **Pipeline → DFD Analysis** in the sidebar.

**Stage 1 — Four input modes:**

- **Paste Mermaid** — live preview with 300ms debounce; "Load example" populates
  a 6-8 node reference DFD (browser → ALB → API → Auth → DB/Cache/S3).
- **Upload file** — drag-drop `.mmd`, `.txt`, `.png`, `.jpg`, or `.json`.
  Image files are passed to Claude Vision.
- **From document** — upload a PDF, DOCX, TXT, or Markdown architecture doc;
  Claude extracts the data flow and produces Mermaid source for review.
- **From description** — paste plain-language system description; Claude
  generates the Mermaid DFD.

**Stage 2 — 4-step SSE progress tracker:**
Parsing diagram → Identifying system components → Mapping attack surfaces →
Generating threat model. Analysis typically takes 20–40 seconds.

**Stage 3 — Split-panel interactive workspace:**

- **Diagram panel** (left, 55%) — Mermaid rendered with custom Nyx theme;
  resizable via drag handle. Click a node to filter threats; hover for
  tooltip with element name and threat count. Zoom with `+`/`−` or scroll wheel.
- **Findings panel** (right, 45%) — severity summary strip; threat cards with
  title, CVSS estimate, STRIDE category, element, description, collapsible
  mitigation, and OWASP/CWE reference pills. Filter by severity and/or STRIDE
  category. "Highlight in diagram →" cross-links cards back to nodes.
- **Cache badge** — ⚡ shown when result was served from the SHA-256 cache.
- **↺ Run again** — re-runs STRIDE with `force=true`, bypassing cache.
- **Improve diagram** — KB-aware completion; adds missing trust boundaries,
  data stores, and services using ingested architecture docs.

**Exports:**

| Format | Content |
| --- | --- |
| Print / Save as PDF | Professional @print layout with cover, diagram, threat table, STRIDE coverage matrix, appendix |
| Annotated `.mmd` | Mermaid source with severity `style` directives |
| Original `.mmd` | Unmodified input source |
| JSON | Metadata wrapper + elements + full threat objects (CVSS, refs, etc.) |

**Threat fields:** id, title, STRIDE category, element, severity (Critical/High/Medium/Low),
CVSS estimate, description, mitigation, OWASP/CWE references.

**Severity colors:** Critical `#DC2626` · High `#EA580C` · Medium `#D97706` · Low `#4F46E5`

### Second brain (Phase 15)

- **Lessons-learned DB** — auto-populated from postmortems, tabletops,
  rejected design reviews; tag-indexed; chat-queryable.
- **Personal ownership dashboard** — claim Service entities; see per-entity
  risk weighted by TM drift, unaddressed threats, expired decisions, open
  postmortem followups.
- **Glossary builder** — extract company-specific jargon, confirm/reject,
  enriches future chat replies.
- **Security philosophy doc** — Tank co-authors a long-running stance doc;
  seeded at Day-30, evolves at Day-60/90/180/365.
- **Security-focused anniversary retros** — fire alongside the generic
  Day-30/60/90/180/365 retros.

### Partner mode (daily cadence)

- **Morning digest** at your `digest_time` — nudges + meetings + follow-ups
  due today.
- **Auto pre-meeting briefs** at 22:00 — generated for tomorrow's
  ICS-imported meetings.
- **Evening journal prompt** at 18:00.
- **Friday weekly reflection** at 16:00.
- **Sunday weekly backup** at 03:00 — `sqlite3.Connection.backup()`,
  rotation keeps last 8.
- **Sunday attack-surface snapshot** at 09:00.
- **Sunday security program snapshot** at 09:30 — persists metrics for the 12-week trend on the program dashboard.

---

## Quickstart (laptop)

```bash
git clone https://github.com/LeSpookyHacker/tank.git tank
cd tank
cp .env.example .env                # paste your ANTHROPIC_API_KEY
./scripts/start.sh                  # creates .venv, installs deps, inits DB, runs uvicorn
# → opens http://localhost:8000
```

The **first run** walks you through a conversational onboarding (role frame,
scope, calendar dump, initial docs, cadence). No forms to fill in. At the end,
you get a printable Day-1 brief.

Requires Python 3.11+ and macOS or Linux. Windows untested.

---

## Recommended setup: dev VM + SSH tunnel

For daily use, run Tank on an always-on dev VM you own and SSH-tunnel from
your laptop. This is the configuration the scheduler / backups / nudges are
designed around.

```bash
# On the VM, one-time:
git clone https://github.com/LeSpookyHacker/tank.git ~/projects/tank
cd ~/projects/tank
cp .env.example .env                       # paste ANTHROPIC_API_KEY
echo 'TANK_ENV=prod' >> .env               # never run --reload under a supervisor
echo 'TANK_TIMEZONE=America/Los_Angeles' >> .env   # your local TZ, NOT the VM's
./scripts/start.sh                         # installs deps + inits DB
# Ctrl-C; then run under systemd:
./scripts/install-systemd.sh
```

The install script registers a `--user` systemd unit with
`Restart=on-failure`, 30s graceful shutdown, sandbox-style isolation
(`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=read-only`), and
`enable-linger` so it survives SSH disconnect.

From your laptop:

```
# ~/.ssh/config
Host tank-vm
  HostName your-dev-vm.example.com
  User you
  LocalForward 8000 127.0.0.1:8000
  ServerAliveInterval 60
  ServerAliveCountMax 5
```

Then `ssh tank-vm` and open `http://localhost:8000`.

**Healthcheck** for monitoring:

```bash
curl http://127.0.0.1:8000/healthz
# {"ok": true, "scheduler": "running", "db": "ok"}
```

Full ops reference: [docs/operations.md](docs/operations.md).

---

## The privacy guarantee

```
┌─────────────────┐   parse    ┌──────────┐   redact    ┌───────────────┐
│  your docs/code │ ─────────► │  chunks  │ ──────────► │ chunks (safe) │
└─────────────────┘            └──────────┘             └───────┬───────┘
                                                                │ embed (local)
                                                                ▼
                          ┌──────────────────────────────────────────┐
                          │   SQLite at ~/.tank/db.sqlite            │
                          │   - chunks (redacted + original)         │
                          │   - entities, relationships              │
                          │   - redaction_map (originals, local-only)│
                          │   - chunks_vec (sqlite-vec) + FTS5       │
                          └──────────────────────────────────────────┘
                                              │
                              retrieve + cache │
                                              ▼
                          ┌──────────────────────────────────────────┐
                          │ prompt: system + KB context (redacted)   │
                          │ ────► Claude Sonnet 4.6 (only model used)│
                          │ ◄──── response (still redacted)          │
                          └──────────────────────────────────────────┘
                                              │
                                  rehydrate locally
                                              ▼
                                        UI / Reports
```

### Redacted by default

- Emails
- Hostnames under `*.<your_internal_tld>`, `*.internal`, `*.corp`, `*.local`,
  `*.lan`, `*.intra`
- Private IPv4 ranges (RFC1918, loopback, link-local, CGNAT) and IPv6 ULA
- AWS account IDs (12-digit near AWS context) and ARNs (account+resource portion)
- GCP project IDs, Azure subscription/tenant UUIDs
- Secret tokens via `detect-secrets` plugins + Shannon-entropy fallback +
  supplemental regex patterns (always on, **non-disableable**, one-way
  SHA-256 hashed). Covered formats include: AWS IAM/STS keys, AWS ARNs,
  GitHub classic PATs (`ghp_...`), GitHub fine-grained PATs (`github_pat_...`),
  GCP API keys (`AIza...`), Azure connection strings, and entropy-detected
  high-entropy strings of any format.

### Off by default (toggle in Settings)

- Public hostnames (often carry useful context — vendor SaaS, cloud regions)
- Public IPs
- Person names (NER + ingested-person wordlist; flipping it on degrades
  conversational utility — requires spaCy on Py 3.10+)

### Verify it yourself

```bash
source .venv/bin/activate
python -m pytest -q                            # 28/28 redaction tests
python -m scripts.verify_privacy --fixture-pack  # after ingest
```

Or pipe outbound traffic through mitmproxy and grep for any fixture
identifier — you'll find zero hits.

### Nuke everything

`Settings → Wipe all` in the UI (requires typing `delete tank` to confirm —
prevents accidental wipes from stale tabs), or:

```bash
rm -rf ~/.tank/
```

Backups in `~/.tank/backups/` are **not** touched by the in-UI wipe —
restore from one if you accidentally wiped.

---

## Theme

Tank ships with the **Nyx** theme — a purple-tinted dark theme inspired by
[github.com/LeSpookyHacker/nyx](https://github.com/LeSpookyHacker/nyx). A
**day/night toggle** in the top-right corner of the navbar swaps to a light
mode with the same iris/amethyst accents. Preference persists in
`localStorage`. New visitors default to `prefers-color-scheme`, falling back
to dark.

The theme uses Inter (sans) + JetBrains Mono (mono) from Google Fonts. On
restricted networks where `fonts.googleapis.com` is blocked, Tank falls back
to the system font stack — UI still works, looks plainer.

---

## Stack

- **Python 3.11+**, FastAPI, Jinja2 + HTMX, Server-Sent Events for streaming.
- **Anthropic SDK** — `claude-sonnet-4-6` for chat, reports, DFD analysis,
  threat models, and all reasoning tasks; `claude-haiku-4-5-20251001` for
  structured-extraction tasks (entity extraction, meeting prep, lesson/journal
  extraction). SDK retry tuned (`max_retries=4`) and per-request timeout
  configurable.
- **SQLite** (WAL) with `sqlite-vec` for vectors and FTS5 for keyword search.
- **`sentence-transformers/all-MiniLM-L6-v2`** for local embeddings — no
  remote embedding API.
- `detect-secrets`, spaCy `en_core_web_sm` (optional), `pypdf`,
  `python-docx`, `pathspec`, `langchain-text-splitters`, `tiktoken`,
  `sse-starlette`, `python-dotenv`.

---

## Configuration

| Var | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | — | Claude API key |
| `TANK_DB_PATH` | no | `~/.tank/db.sqlite` | SQLite location |
| `TANK_INTERNAL_TLD` | no | none | Marks hostnames in this TLD as internal |
| `TANK_BIND_HOST` | no | `127.0.0.1` | Server bind host |
| `TANK_BIND_PORT` | no | `8000` | Server bind port |
| `TANK_API_KEY` | no | unset | Optional static API key. When set, every request must include `X-Tank-Key: <value>`. Strongly recommended if `TANK_BIND_HOST` ≠ `127.0.0.1`. Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `TANK_DIGEST_TIME` | no | `08:00` | Local time for daily nudge run |
| `TANK_ENABLE_PERSON_REDACTION` | no | unset | Set `1` to enable NER-based person redaction |
| `TANK_ENV` | no | `dev` | Set `prod` to disable uvicorn `--reload` (use on any VM) |
| `TANK_TIMEZONE` | no | system | IANA TZ name; **set on a hosted VM** (which is usually UTC) |
| `TANK_API_MAX_RETRIES` | no | `4` | Anthropic SDK retry budget |
| `TANK_API_TIMEOUT_SECONDS` | no | `600` | Per-request ceiling |
| `TANK_DEBUG_TOKENS` | no | off | Set `1` to log per-call token counts (in/out/cache_read/cache_create) to the console |
| `TANK_NYX_API_KEY` | no | unset | Must be set to enable `/api/risks/vuln-intake`; endpoint returns 503 if unset, 401 on wrong key |

---

## Common tasks

```bash
# Bulk ingest a folder
python -m scripts.ingest_cli ~/employer-docs --category architecture

# Inspect the redaction map
sqlite3 ~/.tank/db.sqlite \
  "SELECT category, COUNT(*) FROM redaction_map GROUP BY category;"

# Privacy assertion (after ingest)
python -m scripts.verify_privacy --fixture-pack

# Healthcheck
curl http://127.0.0.1:8000/healthz

# Run the test suite
python -m pytest -q

# Inspect scheduler state (last-fired markers)
sqlite3 ~/.tank/db.sqlite \
  "SELECT job_name, last_label,
          datetime(last_fired_at,'unixepoch','localtime')
   FROM scheduler_state ORDER BY job_name;"

# Inspect backup ledger
sqlite3 ~/.tank/db.sqlite \
  "SELECT path, size_bytes,
          datetime(created_at,'unixepoch','localtime')
   FROM backup_log ORDER BY created_at DESC LIMIT 8;"

# Manually trigger a backup
python -c "from app.claude.scheduler import _take_backup; _take_backup()"

# Wipe everything (UI also supports this with a typed phrase challenge)
rm -rf ~/.tank/
```

---

## Sample data

Tank ships with a synthetic company ("Helix Robotics") in `sample_data/`
so you can test every feature without exposing real data. Two scripts — one
for file ingest, one for DB seeding — are needed for full coverage:

```bash
source .venv/bin/activate
python -m scripts._gen_fixtures             # generate PDF/DOCX/PNG from sources (once)
python -m scripts.load_fixtures --dry-run   # preview what would be ingested
python -m scripts.load_fixtures             # ingest all files — ~$5-10 in Anthropic spend
python -m scripts.seed_db                   # seed DB records — no API cost
```

**What's included:**

- **42 files + 2 repos** — Markdown, PDF, DOCX, PNG/vision, CSV, Sigma rules (4),
  IAM policies (JSON + YAML K8s RBAC), control frameworks (SOC 2 + NIST CSF 2.0),
  and code repo summarization — every parser type exercised.
- **4 DFD Mermaid source files** (`sample_data/dfd/`) — ready to upload into the
  DFD tool's Stage 1 "Upload file" tab. Covers payments-api, identity-svc, pii-vault,
  and webhook-router.
- **DB seed** (`scripts/seed_db.py`) — idempotent; seeds: 3 teams, 4 projects, 2
  pre-cached DFD analyses (18 total STRIDE threats), 4 decisions (2 expiring to
  trigger nudges), 10 unconfirmed glossary terms, 5 lessons, 1 tabletop scenario,
  3 journal entries, and 3 follow-ups. Exercises every living-artifact feature with
  no API calls.

Planted edge cases exercise every redaction category, contradiction surfacing,
gap detection, expiring decisions, and coverage reporting. See
`sample_data/README.md` for the full file inventory, scenario, and spot-check
checklist.

---

## Project status

| Phase | Status | What |
| --- | --- | --- |
| 1-2 | ✅ | Skeleton + redaction engine (28/28 tests) |
| 2.5 | ✅ | Helix Robotics sample data — initial pack (26 files + 2 repos, full parser coverage) |
| 3-7 | ✅ | Ingest, KB, chat, 6 reports |
| 8 | ✅ | Partner mode (daily companion) |
| 9-10 | ✅ | UI polish + privacy assertion |
| 11 | ✅ | Opt-in connectors (folder, ICS, CVE, GitHub) |
| 12 | ✅ | Living threat models + decisions log |
| 13 | ✅ | Workstreams (design reviews, postmortems, tabletops, on-call, weekly digest) |
| 14 | ✅ | Coverage + visibility (Sigma, IAM, compliance, attack surface, ATT&CK) |
| 15 | ✅ | Second brain (lessons, glossary, ownership, philosophy) |
| Ops | ✅ | systemd, healthz, weekly backup, retries, durable scheduler state, wipe phrase |
| UI | ✅ | Nyx theme + day/night toggle |
| 2.1 | ✅ | Markdown rendering in reports + PDF and Markdown export |
| 2.2 | ✅ | Token cost counter fix — all Claude calls tracked across 3 tables |
| 2.3 | ✅ | Claude API optimization — Haiku for extraction tasks, token debug flag |
| 3.1 | ✅ | App redesign — grouped left sidebar nav, empty states |
| 3.2 | ✅ | DFD threat modeling — 4-mode input, SSE progress, split-panel workspace, interactive threat cards, 4 export formats |
| 3.3 | ✅ | Projects dashboard — color/notes fields, card grid UI, detail page, project-scoped chat |
| 3.4 | ✅ | Sample data expansion — 16 new files (arch docs, detections, IAM, compliance, runbook, postmortem), 4 DFD Mermaid sources, `seed_db.py` idempotent DB seed for all living-artifact features |
| Gap 3 | ✅ | Risk register — formal inherent/residual risk tracking, Sonnet KB-grounded assessment, 90-day review scheduling, `get_risk_register` chat tool, `risk_register` report |
| Gap 4 | ✅ | Security program dashboard — 6-domain KPI aggregation, on-demand executive brief (green/yellow/red), 12-week trend snapshots, Nyx vulnerability intake endpoint |
| Gap 5 | ✅ | IR runbooks — per-service 5-phase incident-response playbooks grounded in KB; tabletop integration; postmortem nudge; `find_ir_runbooks` chat tool; Runbook entity registration |
| Security audit | ✅ | Adversarial audit (3 passes, 34 findings) — API-key middleware, CSRF, ReDoS, SSRF/DNS-rebinding, prompt-injection labeling, XSS, privacy contract (10 redaction bypass fixes), parser bombs, FTS5 injection, symlink traversal, secret pattern expansion, input bounds |

Build history with tradeoffs and known gaps: [HISTORY.md](HISTORY.md).

---

## FAQ

For the full FAQ, see [docs/faq.md](docs/faq.md). The short version:

**Does my employer's data leave the machine?**
Only redacted chunks and redacted user prompts go to the Anthropic API. The
redaction map stays on your laptop. Secrets are one-way hashed.

**Why local embeddings?**
So even the redacted content travels through only one external vendor's wire.

**What if Claude is wrong?**
Every fact carries a `source` / `inferred` / `claim` / `user` badge. Click
"this was wrong" on any reply; the correction goes into notes and surfaces
on future retrievals.

**Can I run this on a work laptop without permission?**
Probably not — check your acceptable-use policy. The Anthropic API call
alone may require approval.

**What's with the name?**
Tank in *The Matrix* was the operator who fed the team what they needed from
the outside. Same energy.

---

## Documentation

The full docs live in [docs/](docs/):

- [docs/quickstart.md](docs/quickstart.md) — zero to running in 10 minutes
- [docs/installation.md](docs/installation.md) — local + VM install + systemd
- [docs/configuration.md](docs/configuration.md) — all environment variables, annotated `.env` example
- [docs/concepts.md](docs/concepts.md) — core mental model: entities, chunks, lens, projects
- [docs/first-run.md](docs/first-run.md) — onboarding wizard walkthrough
- [docs/using-tank.md](docs/using-tank.md) — day-to-day workflows
- [docs/architecture.md](docs/architecture.md) — internals deep-dive
- [docs/features/](docs/features/) — per-phase feature reference (includes [projects](docs/features/projects.md), [DFD analysis](docs/features/dfd-analysis.md), [threat models](docs/features/threat-models-decisions.md), [security program + risk register + IR runbooks](docs/features/security-program.md), and more)
- [docs/operations.md](docs/operations.md) — running on a VM, backups, healthz, scheduler
- [docs/faq.md](docs/faq.md) — common questions
- [docs/troubleshooting.md](docs/troubleshooting.md) — known issues and fixes
- [docs/contributing.md](docs/contributing.md) — dev setup, tests, PR process
- [CHANGELOG.md](CHANGELOG.md) — version history

Future-Claude / future-you: [CLAUDE.md](CLAUDE.md) has architecture guidance
for when you're working on the codebase.

---

## License

TBD. Acknowledgements:
[detect-secrets](https://github.com/Yelp/detect-secrets) (Yelp),
[sentence-transformers](https://www.sbert.net/),
[sqlite-vec](https://github.com/asg017/sqlite-vec),
[Nyx](https://github.com/LeSpookyHacker/nyx) (theme inspiration).
