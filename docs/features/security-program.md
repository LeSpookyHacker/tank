# Risk register, security program dashboard & IR runbooks

Three operational features that close the gap for a first security
engineer who needs to track risk formally, show program progress to
leadership, and give on-call engineers per-service incident-response
playbooks.

---

## Risk register (`/risks`)

A formal risk register separate from the decisions log. The decisions
log captures *choices*; the risk register tracks ongoing *exposures* —
inherent likelihood × impact before controls, residual likelihood ×
impact after controls, and a treatment strategy.

### Scoring model

Scores use a 1-5 scale for both likelihood and impact.
`inherent_score = L × I` (1-25); `residual_score = L × I` after
applying known controls.

| Score | Heat label |
| --- | --- |
| ≥ 20 | Critical |
| ≥ 12 | High |
| ≥ 6 | Medium |
| < 6 | Low |

### Treatment options

| Treatment | Meaning |
| --- | --- |
| `mitigate` | Reduce likelihood or impact via controls |
| `accept` | Accept residual risk; link to a decision |
| `transfer` | Shift via insurance or contract |
| `avoid` | Eliminate the risk-bearing activity |

### Creating a risk

From `/risks`, click "Add risk" — fill in title, category, inherent
scores, and optional scope (service entity IDs). Tank immediately
queues a background KB assessment.

### KB-grounded assessment

`POST /api/risks/{id}/assess` calls Sonnet with:
- The service entity card + related chunks
- The latest threat model for the service
- Existing decisions scoped to the service
- The full 1-5 scoring guide

Sonnet returns `residual_likelihood`, `residual_impact`,
`recommended_treatment`, `treatment_rationale`, `control_gaps[]`, and
`suggested_next_steps[]`. Assessments set a 90-day `review_at`
deadline; the `risk_review_due` nudge fires when that deadline passes.

### Chat tool

`get_risk_register(category?, treatment?, limit?)` — returns open risks
ordered by residual score. Use in chat:

- *"What are our top residual risks?"*
- *"Show me all risks we've accepted."*
- *"Which data_breach risks are untreated?"*

### Report kind: `risk_register`

Generates a heat-map narrative from all open risks — inherent vs
residual score distribution, top risks by residual score, control
coverage by category. Available from `/reports` or via subscription.

### Schema

```sql
risks (
    id TEXT PK, title TEXT, description TEXT,
    category TEXT,                   -- data_breach|availability|supply_chain|...
    inherent_likelihood INTEGER,     -- 1-5
    inherent_impact INTEGER,         -- 1-5
    controls_json TEXT,              -- Control entity IDs providing coverage
    residual_likelihood INTEGER,     -- 1-5, set by KB assessment
    residual_impact INTEGER,         -- 1-5, set by KB assessment
    treatment TEXT,                  -- mitigate|accept|transfer|avoid
    treatment_rationale TEXT,
    owner_entity_id TEXT,
    status TEXT,                     -- open|closed|transferred
    review_at INTEGER,               -- Unix epoch; drives nudge
    scope_entity_ids TEXT JSON,
    decision_id TEXT,                -- linked accepted_risk decision (optional)
    created_at INTEGER, updated_at INTEGER,
    project_id TEXT
)
```

### API

| Endpoint | What |
| --- | --- |
| `POST /api/risks` | Create a risk (triggers background assessment) |
| `GET /api/risks` | List (filter: status, category, project_id) |
| `GET /api/risks/{id}` | Detail |
| `POST /api/risks/{id}/assess` | Re-run KB assessment |
| `PUT /api/risks/{id}/status` | Close / reopen |
| `POST /api/vulnerabilities/intake` | Nyx integration hook (see below) |

### Nyx integration hook

Tank exposes `POST /api/vulnerabilities/intake` so
[Nyx](https://github.com/LeSpookyHacker/nyx) can push validated
disclosure findings in without building a full disclosure-triage UI in
Tank:

```json
{
  "cve_id": null,
  "title": "SSRF via redirect in payments-api",
  "description": "...",
  "cvss_score": 7.2,
  "severity": "high",
  "source": "disclosure",
  "affected_service_names": ["payments-api"],
  "external_ref": "HXR-1234"
}
```

Tank redacts `description`, resolves service names to entity IDs, and
creates a `vulnerabilities` row (status=open). The full vulnerability
lifecycle UI is a future addition.

**Authentication:** if `TANK_NYX_API_KEY` is set in the environment,
the endpoint requires the caller to include `X-Nyx-Key: <value>` in
the request headers (compared with `secrets.compare_digest` to prevent
timing attacks). If the env var is not set, the endpoint remains open
for backwards compatibility.

---

## Security program dashboard (`/security-program`)

A single page that aggregates Tank's raw data into leadership-visible
KPIs — no Claude call on page load (instant render), with an on-demand
executive brief button.

### Metric domains

| Domain | Metrics |
| --- | --- |
| Threat models | Total / drifted / updated in last 30 days |
| Vulnerabilities | Open by severity (critical/high/medium/low) / average age (days) |
| Risk register | Open risks / risks with overdue review |
| Compliance | Controls with evidence vs. controls without |
| Incidents | Postmortems published in 90d / open followups / followups done in 90d |
| Design reviews | Open / approved in last 90 days |

### 12-week trend history

The Sunday 09:30 scheduler job calls `take_snapshot()` which writes a
row to `security_program_snapshots` (metrics_json). The dashboard table
shows the last 12 snapshots for trend visibility.

### Executive brief

Click "Generate executive brief" → Tank calls Sonnet with the current
metrics snapshot and the `executive_security_brief.md` prompt → returns:

- `program_health`: `green` | `yellow` | `red`
- `headline`: one-sentence program status
- `key_achievements[]`: bullet list of recent wins
- `top_risks[]`: top 3-5 risks to surface to leadership
- `recommended_priorities[]`: what to focus on next
- `summary_md`: full 1-page Markdown brief suitable for a board update

The brief is rendered inline with `marked.js` — copy and paste into a
slide deck or share as-is.

### API

| Endpoint | What |
| --- | --- |
| `GET /api/security-program/metrics` | Current metric snapshot (JSON) |
| `POST /api/security-program/executive-brief` | Generate Sonnet executive brief |
| `GET /api/security-program/history` | Last 12 weekly snapshots |

---

## IR runbooks (`/ir-runbooks`)

Per-service, per-scenario incident-response playbooks grounded in your
KB. The goal: a 3am on-call engineer can follow the runbook without
asking anyone.

### Structure

Each runbook has five phases:

| Phase | Icon | What it covers |
| --- | --- | --- |
| Detect | 🔍 | Signals that confirm the incident; detection queries; alert correlation |
| Contain | 🛑 | Immediate containment steps with time-box; decision points |
| Eradicate | 🧹 | Root-cause removal; success criteria |
| Recover | ♻️ | Service restoration; validation steps; rollback decision points |
| Comms | 📢 | Stakeholder notification template; escalation path |

Each phase lists concrete steps, decision points (if/then branches),
a time-box recommendation, and a success criterion.

### Generating a runbook

From `/ir-runbooks`, fill in:
- **Service** — service entity from the KB (optional but highly recommended)
- **Threat scenario** — plain-English description (e.g. "credential
  stuffing on the auth endpoint")
- **Severity trigger** — sev1 / sev2 / sev3 / any

Tank queries the KB for:
- Service entity card + linked chunks (architecture, dependencies, data stores)
- Latest threat model threats for the service
- Most recent postmortem body (for prior-incident context)
- Hybrid KB search on the threat scenario (runbooks, detections, controls)

Sonnet generates the 5-phase runbook with `thinking={"type":
"adaptive"}`. Generation takes 20-60 seconds. The runbook is stored
and registered as a `Runbook` entity with a `has_control` edge to the
service so the KB graph reflects it.

### Tabletop → runbook

On the tabletop detail page, a collapsible "Generate IR runbook from
this scenario" section pre-populates the service and threat kind from
the tabletop. After running a drill, generate the runbook in one click.

### Postmortem → runbook nudge

When a postmortem is published, Tank checks `services_affected` against
`ir_runbooks_store.services_with_runbook()`. Any affected service that
lacks a runbook receives a `missing_ir_runbook` nudge so the gap is
visible on the Today dashboard.

### Chat tool

`find_ir_runbooks(service_name?, service_id?, limit?)` — use in chat:

- *"What's the runbook for a credential stuffing attack on identity-svc?"*
- *"Do we have a runbook for payments-api?"*
- *"List all confirmed runbooks."*

### Confirming a runbook

After reviewing a runbook, click "Confirm" to set
`confirmed_by_user=1`. Unconfirmed runbooks are shown with a warning
badge — they're machine-generated and should be validated before a
real incident.

### Export

The runbook detail page has print CSS (`@media print`) for a
professional PDF export with the runbook rendered in full — suitable
for printing and storing in an offline incident-response binder.

### Schema

```sql
ir_runbooks (
    id TEXT PK,
    service_entity_id TEXT,      -- FK entities (optional)
    threat_scenario TEXT,
    severity_trigger TEXT,       -- sev1|sev2|sev3|any
    runbook_md TEXT,             -- rehydrated (display)
    runbook_md_redacted TEXT,    -- redacted (audit)
    contacts_json TEXT,          -- escalation chain [{name_placeholder, role, channel}]
    escalation_json TEXT,        -- trigger conditions by tier
    version INTEGER,
    generated_at INTEGER,
    confirmed_by_user INTEGER,   -- 0 = unconfirmed, 1 = confirmed
    tabletop_id TEXT,            -- FK tabletops (if derived from a tabletop)
    project_id TEXT
)
```

### API

| Endpoint | What |
| --- | --- |
| `POST /api/ir-runbooks/generate-sync` | Generate + redirect to new runbook (blocking) |
| `POST /api/ir-runbooks/generate` | Generate in background (returns runbook_id) |
| `GET /api/ir-runbooks` | List (filter: service_entity_id) |
| `GET /api/ir-runbooks/{id}` | Detail |
| `POST /api/ir-runbooks/{id}/confirm` | Mark confirmed |
| `DELETE /api/ir-runbooks/{id}` | Delete |
| `POST /api/tabletops/{id}/generate-runbook` | Generate runbook from tabletop |
