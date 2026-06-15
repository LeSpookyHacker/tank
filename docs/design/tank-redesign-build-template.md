# Tank — Redesign Build Prompt
# Populated from TANK_EVALUATION.md (generated 2026-05-28, commit b92ab25)

This document was built directly from `TANK_EVALUATION.md`. Before running this prompt,
Claude Code must read `TANK_EVALUATION.md` in full — it is the authoritative record of
what exists, what was decided, and why. Do not proceed past Phase 0 without doing so.

---

## Context: What Tank Is Becoming

Tank is being redesigned around a single persona:

> You are the first security engineer the company has ever hired. There is no security
> program, no documentation, no asset inventory, and no existing security culture. It is
> entirely up to you to discover what the company has built, assess the risk, and build a
> security program from nothing.

The gap between the old Tank and the new Tank is not primarily a feature gap — it is a
philosophy gap. The old Tank *amplifies* an existing signal: you bring it documents, it
makes them queryable. The first hire has no documents to bring. Tank must now be able to
*generate* the signal from nothing — from a structured intake interview, from conversations
with engineers, from an org scan, from answers to twenty direct questions on Day 1.

Three things change fundamentally:
1. **Bootstrapping** — Tank must provide value from the moment someone opens it, with no
   pre-existing KB.
2. **Prioritization** — Tank must answer "out of everything I found, what do I fix first?"
   with a concrete, opinionated recommendation.
3. **Communication** — Tank must produce leadership-ready outputs without the engineer
   having to translate them manually.

What does NOT change: the privacy contract, the knowledge graph model, the tenure-aware
lens (Map → Prioritize → Execute → Maintain), and the daily companion cadence. These are
exactly right for this persona. The foundation is correct. The missing pieces are the
front door and the output layer.

Read Section 5 of `TANK_EVALUATION.md` ("What Tank Becomes") now. That narrative is the
north star for this entire build.

---

## PHASE 0 — Pre-Build Audit (No code yet)

Before writing any code:

1. Re-read `TANK_EVALUATION.md` in full.
2. Work through the feature verdict table (Section 2) and confirm your understanding of
   every KEEP, KEEP & EVOLVE, and NEW verdict. This is your checklist.
3. Confirm the build order from Section 7. That is the sequence you will follow.
4. Note every feature with no verdict change (KEEP). These are wired into the new
   architecture without functional modification.
5. Note every NEW feature. These have no existing code — build them from scratch.
6. Present a one-page implementation plan before writing anything: proposed data model
   changes, any new routes, and the order in which you will tackle each phase.

---

## PHASE 1 — Data Model Updates

### 1.1 — New and Modified Entities

The following changes to the data model are required to support this redesign:

**New entities:**
- `intake_interview` — stores answers from the quick-start intake interview. Fields:
  `id`, `created_at`, `completed_at`, `answers` (JSON blob of question/answer pairs),
  `kb_seeded` (bool — whether answers have been converted to entity stubs).
- `asset_inventory` — represents the security stack audit. Fields: `id`, `created_at`,
  `updated_at`, `capability_category` (identity / MFA / secrets / SIEM / WAF / EDR /
  vuln_scanner / DLP / network_seg / backup / logging / patching), `tool_name` (nullable),
  `deployment_status` (none / partial / full), `coverage_notes`, `known_gaps`.
- `ninety_day_plan` — the generated task list. Fields: `id`, `created_at`, `generated_at`,
  `items` (JSON array of tasks with week number, title, description, done bool, and
  source — intake / kb_state / manual).
- `leadership_report` — new report kind distinct from existing report types. Fields: `id`,
  `kind` (state_of_security / initial_assessment / program_roadmap / risk_translation),
  `generated_at`, `content_md`, `project_id` (nullable — some are org-level).
- `policy_artifact` — a living policy document. Fields: `id`, `kind` (acceptable_use /
  incident_response / secure_sdl / vulnerability_management / data_classification),
  `created_at`, `updated_at`, `content_md`, `status` (draft / reviewed / approved),
  `linked_decision_ids` (array).

**Modified entities:**
- `org_profile` — add fields: `industry`, `customer_type`, `approx_team_size`,
  `compliance_targets` (array), `intake_completed` (bool), `kb_bootstrap_stage`
  (none / intake_done / discovery_done).
- `chat_session` — add field: `mode` (enum: normal / discovery). Discovery mode activates
  when KB chunk count is below threshold (define as a configurable constant, default 10).
- `project` — add `starter_template` (bool) to flag auto-created template projects from
  onboarding.
- `vulnerability` — add fields: `triage_status` (new / triaged / assigned / closed),
  `assigned_to` (nullable string), `due_date` (nullable date), `promoted_to_risk_id`
  (nullable FK to risk register).

### 1.2 — Preserved Entities

The following entities are carried forward with no functional changes. Wire them into
the new architecture cleanly:

Living threat models, decisions log entries, lessons DB entries, anniversary retros,
risk register entries, IR runbooks, workstream artifacts (postmortems, tabletops),
design review records, glossary entries, security philosophy doc, coverage records
(Sigma, IAM, compliance evidence), attack surface snapshots, entity graph nodes and
relationships, KB chunks and provenance records, watcher configs.

### 1.3 — Migration

Write a migration script that:
- Preserves all existing data without exception
- Sets `intake_completed = false` and `kb_bootstrap_stage = none` on all existing orgs
  (they will be offered the intake interview from the dashboard on next login)
- Sets `triage_status = new` on all existing vulnerability records
- Logs a full migration report to the console on completion
- Does not delete or rename any existing tables

---

## PHASE 2 — Quick-Start Intake Interview (NEW — Highest Priority)

This is the front door. It is the single most important feature in this entire redesign.
Without it, Tank cannot serve the first hire at all. Build this before anything else in
Phases 3–8.

### What It Does

A guided 10–15 minute structured interview that asks the first hire ~20 direct questions
about their company before any documents are uploaded. On completion it:
- Seeds the entity graph with stubs for the services, teams, data types, and tools
  mentioned in the answers
- Generates an initial risk hypothesis (top 3 probable risk areas based on company
  profile)
- Produces a Day-1 Brief — the existing Day-1 brief report kind, but now runnable from
  intake answers alone, with no KB documents required
- Sets `intake_completed = true` and `kb_bootstrap_stage = intake_done` on the org profile

### When It Appears

- **First-time user** (no org profile, or `intake_completed = false`): the intake
  interview launches automatically after login, before the dashboard is shown. It is not
  skippable on first login — the user must complete at least the first 5 questions before
  they can proceed. The remaining questions can be deferred.
- **Returning user who skipped**: a prominent "Complete your setup" card on the home
  dashboard with a "Start intake interview" CTA.
- **On demand**: accessible from Settings > Organization > "Re-run intake interview"
  at any time.

### The 20 Questions

Present these as a conversational flow — one question at a time, not a long form. Each
question has a freetext answer field. Some have optional structured helpers (dropdowns,
multi-select chips) the user can use instead of typing.

```
1.  What does your company build? (product/service description)
2.  Who are your customers? (consumers / SMB / enterprise / government / internal)
3.  What sensitive data does the company handle?
    [chips: PII / payment card data / health data / financial records /
     credentials / IP / regulated data / none I'm aware of]
4.  What cloud providers does the company use?
    [chips: AWS / GCP / Azure / on-prem / other]
5.  What are the names of your most important services or applications?
    (freetext — comma separated, or one per line)
6.  Who owns those services? (team names or individual names)
7.  How large is the engineering org?
    [chips: 1–10 / 11–50 / 51–200 / 200+]
8.  Does the company have an identity provider (e.g. Okta, Google Workspace)?
    [yes + name / no / not sure]
9.  Is MFA enforced for internal systems?
    [yes, everywhere / yes, some systems / no / not sure]
10. Does the company have a secrets manager (e.g. Vault, AWS Secrets Manager)?
    [yes + name / no / not sure]
11. Are there any existing security tools in place?
    (freetext — e.g. "we have Snyk, no SIEM, no WAF")
12. Has the company ever had a security incident or breach?
    [yes / no / not sure — if yes, brief description]
13. Is there any existing compliance requirement or obligation?
    [chips: SOC 2 / ISO 27001 / PCI-DSS / HIPAA / GDPR / None / Not sure]
14. Do any enterprise customers require compliance evidence as a condition of contract?
    [yes / no / not sure]
15. What is the company's primary programming language or stack?
    (freetext)
16. Where does the company's code live?
    [chips: GitHub / GitLab / Bitbucket / Other / Not sure]
17. Does the company have a staging/production separation?
    [yes / no / not sure]
18. Is there a disaster recovery or backup process for critical data?
    [yes / no / not sure]
19. What does your manager or leadership expect from you in the first 90 days?
    (freetext — this seeds the 90-day plan priorities)
20. What are you most worried about security-wise right now?
    (freetext — this seeds the initial risk hypothesis)
```

### Entity Seeding from Answers

After the interview is complete, parse the answers and create entity stubs:
- Each service/application named in Q5 → `ServiceEntity` stub (status: unconfirmed)
- Each team named in Q6 → `TeamEntity` stub
- Cloud providers from Q4 → `InfrastructureEntity` stubs
- Data types from Q3 → `DataTypeEntity` stubs
- Tools named in Q11 → `ToolEntity` stubs (security tooling)
- Identity provider from Q8 → `ToolEntity` stub (type: identity)

Mark all stubs with `source: intake_interview` and `confidence: low` so the entity
browser can visually distinguish confirmed (ingested) entities from seeded (interview)
entities.

### Day-1 Brief Generation

Modify the existing Day-1 brief generator to accept intake answers as a valid context
source — not just ingested KB documents. When `intake_completed = true` and KB chunk
count is less than 10, generate the brief from intake answers directly.

The brief should produce:
- Top 3 probable risk areas (derived from company profile — e.g., payment data + no WAF
  → payment surface risk)
- Week 1 priority meeting list (generated from team names in Q6)
- A preliminary reading list tailored to the industry and stack
- A "what I don't know yet" list — the questions Tank could not answer from the intake
  alone, flagged for the first hire to investigate

---

## PHASE 3 — Onboarding Flow Revision (KEEP & EVOLVE)

The current onboarding configures a companion for someone who already knows their
context. The new onboarding conducts a discovery interview.

### Changes

- **Remove from onboarding:** role selection, internal TLD configuration, digest time
  selection. Move all of these to Settings > Preferences.
- **Replace with:** the Quick-Start Intake Interview from Phase 2. The onboarding flow
  IS the intake interview, with a brief welcome screen before it:

  > "Welcome to Tank. Before we do anything else, let's build your starting point.
  > I'm going to ask you ~20 questions about your company. You don't need any documents —
  > just answer from memory. Estimates and guesses are fine; we'll refine everything as
  > we go. This takes about 15 minutes."

- **After intake completion:** show a brief "You're set up" screen with three items:
  1. A link to the generated Day-1 Brief
  2. The skeleton entity graph (animated, shows the stubs that were just created)
  3. A "What to do next" card pointing to the Org Discovery Wizard

- **Returning users who bypassed onboarding** (existing users): on next login, show a
  non-blocking banner on the home dashboard: "Tank works better with your company context.
  [Run the intake interview →]" Dismissible, re-appears after 7 days if not acted on.

---

## PHASE 4 — Chat Empty-KB Mode (KEEP & EVOLVE)

This is a behavioral change to the existing chat loop, not a new feature. It must ship
in Phase 1 alongside the intake interview.

### Trigger Condition

When a chat session is opened and the KB chunk count is below the configured threshold
(default: 10 chunks), set `chat_session.mode = discovery`.

### Discovery Mode Behavior

In discovery mode, the chat loop changes as follows:

- **Before retrieval:** check KB chunk count. If below threshold, skip the standard
  retrieval step and instead prepend a discovery-mode system prompt:

```
You are Tank operating in discovery mode. The user's knowledge base is sparse or empty.
Your job is not to retrieve and synthesize existing information — it's to help the user
build their initial picture of their company's security landscape.

In this mode:
- Acknowledge directly what you don't know ("I don't have any information about that
  service yet — can you tell me more?")
- Ask one clarifying question per response when relevant
- When the user provides new information in conversation (a service name, a tool, a
  team name), treat it as provisional KB data and acknowledge it: "I've noted that you
  use Vault for secrets management — I'll carry that into our next conversation"
- Surface suggestions for what to ingest: "If you can share the Terraform configs for
  that service, I can give you a much more specific risk assessment"
- Do not pretend to have KB context you don't have
```

- **Provisional entity capture:** when the user mentions a service, tool, team, or data
  type in chat that does not exist in the entity graph, Tank surfaces a confirmation chip
  at the end of the response: "Add 'Payments API' as a service entity? [Confirm] [Skip]"
  Confirmed items are added as entity stubs with `source: chat_discovery`.

- **Visual indicator:** show a subtle "Discovery mode — KB building" badge in the chat
  header. Disappears once KB chunk count exceeds threshold.

- **Mode transition:** when KB chunk count crosses the threshold, the next chat session
  opens in normal mode. No abrupt mid-session switch.

---

## PHASE 5 — Org Discovery Wizard (NEW)

A guided workflow to help the first hire systematically discover and inventory what
exists. Accessible from: post-onboarding "What to do next" card, the Entity Browser
empty state, and the home dashboard during the Discovery tenure phase.

### Step 1: GitHub Org Scan

- Input: GitHub org name and a personal access token (read-only, `repo` scope)
- On submit: enumerate all repos in the org. For each repo fetch: name, description,
  primary language, last commit date, visibility (public/private)
- Display results as a checklist. Each repo has a suggested action:
  - "Ingest" (adds to ingestion queue), "Skip" (mark as out of scope), "Note only"
    (creates a repo entity stub without ingesting content)
- Pre-check repos that look like production services (heuristic: not archived, committed
  within 90 days, not named with common non-service patterns like `-docs`, `-config`,
  `-terraform`)
- On confirm: create `RepositoryEntity` stubs for all selected repos; add "Ingest"
  selections to the document ingestion queue

### Step 2: Team Directory Import

- Accept: CSV upload (columns: name, email, team, role) or manual entry form
- On import: create `PersonEntity` and `TeamEntity` stubs from the data
- Display a preview table before confirming. Let the user edit team names and merge
  duplicates
- On confirm: persist entities with `source: directory_import`

### Step 3: Manual Service Entry

- A structured form for entering services discovered in conversation or investigation
- Fields: service name (required), type (web app / API / mobile / data store /
  infrastructure / internal tool / third-party), owning team (dropdown from discovered
  teams), tech stack (freetext), notes
- "Add another" flow — the user stays in the form until they've entered everything
  they know
- On save: create `ServiceEntity` stubs with `source: manual_discovery`

### Step 4: Summary

After all three steps, show:
- Total entities created
- Ingestion queue count ("N repos queued for ingestion")
- A "Start ingesting" CTA that opens the document ingestion UI with the queue pre-loaded
- An "I'm done for now" option that dismisses to the entity browser

---

## PHASE 6 — Security Stack Audit Template (NEW)

A structured inventory covering 12–15 security capability categories. Accessible from:
the Security Program Dashboard (new "Stack Audit" section), the home dashboard during
Discovery phase, and the entity browser.

### Capability Categories

For each of the following, the user records: current tool or "None", deployment status
(None / Partial / Full), coverage notes, and known gaps.

```
1.  Identity Provider (SSO/LDAP)
2.  Multi-Factor Authentication
3.  Secrets Management
4.  SIEM / Log Aggregation
5.  Web Application Firewall (WAF)
6.  Endpoint Detection & Response (EDR)
7.  Vulnerability Scanner
8.  Data Loss Prevention (DLP)
9.  Network Segmentation
10. Backup & Recovery
11. Patch Management
12. Security Training Platform
13. Bug Bounty / Penetration Testing
14. Container / Supply Chain Security
15. Cloud Security Posture Management (CSPM)
```

### Storage and Usage

- Saved as a single `asset_inventory` record per org, updated in place
- Displayed as a table on the Security Program Dashboard with a completion percentage
  ("9 of 15 categories assessed")
- Fed to the Prioritization Engine as context: categories marked "None" with no
  compensating control flag gaps that increase risk scores
- The morning digest includes a nudge during Discovery phase: "You haven't completed your
  security stack audit yet. [Start now →]"

---

## PHASE 7 — Features from the Verdict Table

Work through every KEEP & EVOLVE feature from `TANK_EVALUATION.md` Section 2.
For KEEP features: wire into new architecture with no functional changes.

### KEEP & EVOLVE: Document Ingestion

Current behavior: parses PDF, DOCX, MD, CSV, JSON, YAML, PNG, Git repos into a typed KB.

Evolution:
- Add org-level ingestion (not scoped to a project). Documents ingested at org level
  (architecture overviews, past audit reports, general policies) populate the global KB
  and are available as context in all Claude calls across all projects.
- Add a `document_kind` tag on ingest: Architecture / Security Policy / Audit Report /
  Pen Test / Runbook / Compliance / Configuration / Other. Claude uses this to adjust
  its analysis prompt per kind.
- When the ingestion queue is pre-loaded from the Org Discovery Wizard (Phase 5), show
  a "Process queue" view — not just a single upload zone — with a batch progress tracker.
- Add "zero-doc fallback" messaging in the ingestion UI empty state: "Nothing to upload
  yet? [Start the intake interview →] to build your starting point from a conversation."

### KEEP & EVOLVE: Chat with KB

Current behavior: streaming chat with 15 tools; retrieves chunks + entity cards.

Evolution:
- Add discovery mode as specified in Phase 4
- Add a "chat mode" selector visible at the top of the chat panel:
  [General] [Threat Analysis] [Policy Drafting] [Explain This Finding] [Meeting Prep]
  Each mode sets a different system prompt prefix that primes Claude for that task type.
  Mode selection is optional — users can ignore it and chat freely.
- In Meeting Prep mode: Tank uses entity graph + decisions log to generate pre-meeting
  context about a named team or person. Prompt: "I'm meeting with the SRE team tomorrow."
  Tank responds with: what it knows about that team's services, current open risks
  attributable to their stack, suggested questions to ask, and relevant open decisions
  they may be able to answer.
- Project-scoped chat: prepend `project.notes` to the system prompt when chat is opened
  from within a project. If notes are empty, omit.

### KEEP & EVOLVE: Entity Graph

Current behavior: 14 entity types, 9 relationship kinds, graph visualization.

Evolution:
- Add seeding path: intake interview answers and org discovery wizard results create
  entity stubs. Stubs are visually distinct from confirmed (ingested) entities in the
  graph view — use a dashed border or muted color for stub nodes.
- Entity browser empty state: replace blank table with a CTA — "Your entity graph is
  empty. [Run the intake interview →] or [Start the org discovery wizard →]"
- Add confidence field to entity records: low (from intake/chat), medium (from
  discovery wizard), high (from ingested documents). Display as a small indicator on
  entity cards.
- "Claim ownership" flow during Discovery phase: after entities are seeded, the
  Ownership Dashboard (/me) prompts the user to claim ownership of each discovered
  service. Do not show an empty ownership table — show a "Services waiting for owner
  assignment" list.

### KEEP & EVOLVE: Reports (11 kinds + 3 new)

Current behavior: 11 report kinds generated from KB.

Evolution:
- Add three new report kinds to the `REPORT_REGISTRY` (follow existing pattern in
  `reports.py`):
  1. **State of Security** (`state_of_security`) — monthly one-page brief. Business
     language. Written for a CTO/CFO/board reader. Contents: program health summary,
     top 3 active risks with business impact statements, actions taken this month,
     actions planned next month. Generated from risk register + decisions log +
     program dashboard KPIs.
  2. **Initial Assessment** (`initial_assessment`) — the 30-day findings brief.
     Contents: what was discovered, top 10 findings with business impact framing
     (not just CVSS descriptions), compliance gap summary, recommended immediate
     actions with effort estimates. Available after `tenure_days >= 14`.
  3. **Program Roadmap** (`program_roadmap`) — 12-month plan. Contents: where we
     started (Day 1 baseline), where we are now, 4-quarter milestone plan with
     investment requirements and risk reduction narrative. Generated from KB + risk
     register + 90-day plan items. Available after `tenure_days >= 45`.
- All existing reports that return empty or near-empty results from a sparse KB should
  display a graceful fallback state: "This report needs more KB context. Here's what
  you can ingest to make it useful: [suggested document types]."
- Modify the Day-1 Brief generator to work from intake answers alone (see Phase 2).

### KEEP & EVOLVE: DFD + Threat Modeling

Current behavior: 4-mode input, SSE progress, split-panel workspace, STRIDE + CVSS,
PDF export.

Evolution (in addition to everything in `tank-dfd-threatmodel-revamp.md`, which applies
in full):
- DFDs are now linkable to a specific service entity in the entity graph. When submitting
  a DFD, offer a "Link to service" dropdown populated from known services. The threat
  model findings are then associated with that service entity and appear in its entity
  card.
- Add "Generate DFD from service documents": if a service entity has associated ingested
  documents, show a "Generate DFD" button on the service entity card. This runs the
  existing doc-to-Mermaid generation and drops the user into the DFD editor for review.
- Add "discovery mode" annotation: if the DFD was built from partial knowledge (stubs,
  intake answers), add a visual watermark or banner: "This diagram contains inferred
  components. Treat threat findings as preliminary until diagram is confirmed."
- Threat model findings feed directly into the risk register: after a threat model
  completes, prompt "Add findings to risk register? [Select all / Select individually]"

### KEEP & EVOLVE: Decisions Log

Current behavior: design choices, accepted risks, deferred fixes, security invariants;
expiry + reaffirmation.

Evolution:
- Increase UX prominence during early tenure: in the Discovery and Assessment tenure
  phases, the Decisions Log should appear on the home dashboard as a "Recent decisions"
  strip (last 3 entries), not just in the sidebar.
- Every generated policy artifact (Phase 8) automatically creates draft decisions log
  entries for the implicit design choices within it (e.g., adopting NIST CSF → decision
  entry of kind `design_choice`). The user confirms or edits these entries.
- Add a "founding decisions" tag for entries made during the first 90 days. These are
  especially important for audit trails.

### KEEP & EVOLVE: Security Program Dashboard

Current behavior: 6-domain KPI aggregation, on-demand exec brief, 12-week trends.

Evolution:
- Add a "Building from zero" mode that activates when `tenure_days < 90`. In this mode,
  the dashboard leads with trajectory and intent — not just current state:
  - Show a "Day 1 baseline vs today" comparison panel (requires capturing a snapshot
    at intake completion — do this automatically)
  - Replace the "current state is red" framing with "here's the progress trajectory"
    framing: "Risk register: 0 → 28 items catalogued (12 closed). Threat models: 0 → 4
    completed."
  - Add a program stage indicator: Discovery / Assessment / Foundation / Program with
    a checklist for each stage accessible on click
- Add the Security Stack Audit completion percentage (from Phase 6) as a dashboard panel
- Add vulnerability management stats from Phase 9: open vuln count, mean-time-to-close
  (once triage workflow has data)

### KEEP & EVOLVE: Partner Mode (digest, journal, nudges, meeting prep)

Current behavior: morning digest, pre-meeting briefs, evening journal prompt, Friday
reflection.

Evolution:
- Add first-hire-specific nudge kinds. Implement these as new entries in the nudge
  registry (follow existing nudge pattern):
  - `first_hire_team_meeting` — fires if a team entity exists with no associated
    meeting record in the last 14 days: "You haven't met with [team name] yet. [Prep
    meeting notes →]"
  - `first_hire_top_service_tm` — fires at Day 14 if no threat model exists for any
    service: "Week 2 milestone: run a threat model for your highest-risk service. [Start →]"
  - `first_hire_day30_check` — fires at Day 28: "Day 30 is approaching. Have you
    identified your top 5 risks? [Open prioritization engine →]"
  - `intake_incomplete` — fires daily until intake is complete: "Complete your company
    intake to unlock your Day-1 Brief. [Continue →]"
  - `stack_audit_incomplete` — fires weekly during Discovery phase until stack audit
    is complete
  - `first_policy_draft` — fires at Day 45 if no policy artifacts exist: "You're in
    the Foundation phase. Time to draft your first security policies. [Generate →]"
- Morning digest during Discovery phase should lead with the 90-Day Plan's current week
  tasks, not just decayed entities.

### KEEP & EVOLVE: Day-1 Brief

Current behavior: Sonnet-generated brief from role + scope; requires some KB context.

Evolution:
- Remove the KB context requirement. The brief must generate from intake answers alone
  when KB is sparse (see Phase 2).
- Structure the brief into four sections:
  1. What I know (from intake and any ingested docs)
  2. What I think the top risks are (preliminary, from intake answers)
  3. Who to meet in week 1 and what to ask them (from team entities)
  4. What I don't know yet (explicit gap list)
- Add a "Regenerate brief" button that re-runs the generation as the KB grows. The brief
  is most useful on Day 1 and Day 14 — surface regeneration CTAs at both points.

### KEEP & EVOLVE: Projects

Current behavior: scoped workspaces with doc/conversation/report segregation.

Evolution:
- Add starter project templates. When a user creates their first project (or from the
  Org Discovery Wizard), offer: "Start with suggested project structure?" Templates:
  - "Core Infrastructure"
  - "Customer-Facing Services"
  - "Internal Tools"
  - "Compliance & Governance"
  Each template pre-populates the project with a description, suggested tags, and a
  starting notes template.
- Template projects are flagged with `starter_template = true` and shown with a
  "Getting started" badge until the user has ingested at least one document into them.

### KEEP & EVOLVE: Watchers (folder/ICS/CVE/GitHub)

Current behavior: monitors for changes across configured sources.

Evolution:
- Add GitHub org-level discovery to the GitHub repo watcher: when a GitHub token is
  configured (from Org Discovery Wizard), the watcher scans for new repos added to the
  org and surfaces them as "New repo discovered: [name]. [Review and ingest? →]"
- CVE watcher: when a new CVE matches a tool or library in the entity graph, surface it
  with an entity-mapped summary: "New CVE CVE-2025-XXXX affects [Library Name], which
  is used by [Service Name]. [Review →]"

### KEEP & EVOLVE: Ownership Dashboard (/me)

Current behavior: claimed service entities with risk scores.

Evolution:
- During Discovery phase (`tenure_days < 14`): replace the empty table with a
  "Services waiting for owner assignment" list, populated from entity stubs.
  CTA: "Claim ownership of services as you discover them."
- Risk score computation: already correct for mature state. For stub entities
  (confidence: low), show "Risk score pending — complete threat model to compute."
- Add a "My open actions" panel to the /me dashboard: all risk register items,
  vulnerability triage assignments, and 90-day plan tasks assigned to or owned by
  the current user, in one place.

---

## PHASE 8 — Security Policy Scaffolding (NEW)

Five first-draft policies generated from the KB, stored as living artifacts in Tank.
Accessible from: the Foundation phase checklist, the Security Program Dashboard, and
a new "Policies" section in the left navigation.

### The Five Policies

For each policy kind, Tank generates a first draft using the org profile + entity
graph + compliance targets as context. The drafts use the company's actual service
names, cloud providers, authentication systems, and data types — not generic
placeholders.

```
1. Acceptable Use Policy
2. Incident Response Policy
3. Secure Development Lifecycle (SDL) Policy
4. Vulnerability Management Policy
5. Data Classification Policy
```

### Generation Flow

1. User clicks "Generate [policy name]" from the Policies section
2. Tank shows a brief pre-generation summary: "I'll generate this policy using your
   company context. I know about [N] services, [cloud providers], and your target
   compliance framework [SOC 2 / etc.]. Proceed?"
3. Generation runs via Claude with the org profile + relevant KB entities as context
4. Output renders in an inline editor (Markdown, rendered view with edit-raw toggle)
5. User edits, then clicks "Mark as reviewed" to promote status from draft → reviewed
6. On save: Tank creates draft decisions log entries for the implicit design choices
   in the policy (e.g., "Minimum password length: 12 characters" → decision entry)

### Storage

- Each policy is stored as a `policy_artifact` record
- Version history is tracked (append new versions, never overwrite)
- Policies are linked to relevant service entities in the entity graph
- Exportable as PDF or DOCX from the policy detail view

### Navigation

Add "Policies" to the left navigation, below "Reports." Shows a list of all five
policy kinds with their current status (Not started / Draft / Reviewed / Approved).

---

## PHASE 9 — Vulnerability Management Workflow (KEEP & EVOLVE)

Triage UI for the existing `vulnerabilities` table. This extends what exists — it does
not replace it.

### Triage Queue

A new view at `/vulnerabilities` (or within the Security Program Dashboard). Shows all
vulnerability records with `triage_status = new`.

Each queue item shows: CVE ID (if applicable), affected service (from entity graph),
CVSS score, source (CVE feed / scanner / manual), date discovered.

Actions per item:
- **Triage**: set severity assessment, add notes, confirm affected services. Moves
  status to `triaged`.
- **Assign**: set owner (freetext) and due date. Moves status to `assigned`.
- **Close**: mark as remediated, accepted risk, or not applicable. Moves status to
  `closed`. If "accepted risk": prompt to add a risk register entry.
- **Promote to risk register**: for high/critical CVEs that represent strategic risk,
  not just operational patching.

### Program Dashboard Integration

Add to the Security Program Dashboard:
- Open vulnerability count (total, by severity)
- Mean-time-to-close (rolling 90-day average)
- Vulnerability aging chart (how long items have been in triage)

### Nudges

- Weekly nudge if triage queue has items older than 7 days: "You have [N] untriaged
  vulnerabilities. [Review queue →]"
- `first_hire_vuln_process` nudge at Day 45: "Foundation phase: set up your
  vulnerability management process. [Open triage queue →]"

---

## PHASE 10 — Prioritization Engine (NEW)

Given a risk register with N items across M services, what do you fix first?

Accessible from: a new "Priorities" section on the Security Program Dashboard, and
via chat ("what should I focus on this quarter?").

### Input Sources

The prioritization engine takes the following as inputs:
- All risk register entries (inherent score, residual score, treatment status)
- Entity graph (service criticality, data types handled, team ownership)
- Security stack audit results (which compensating controls exist — if WAF is "None",
  web-facing service risks score higher)
- Compliance targets (risks that create regulatory exposure rank higher)
- Vulnerability triage queue (open high/critical CVEs feed into prioritization)

### Output

A concrete quarterly action plan: the top 5 items to address this quarter. For each:
- Risk title and affected service
- Why this is in the top 5 (plain-language rationale: not a score, a sentence)
- What "done" looks like (specific, testable outcome)
- Estimated effort (Days / Weeks / Months)
- Owner (from entity graph service ownership)

This is generated by Claude using a structured prompt with all inputs above as context.
The recommendation must be opinionated — it cannot hedge into "it depends." If Claude
attempts to produce a hedge, the prompt should explicitly reject it: "Give the top 5.
If you're uncertain between two items, pick the higher-risk one and explain why."

### Regeneration

The prioritization engine output is cached and shown with a "Generated [date]" label.
A "Regenerate" button re-runs it. Monthly nudge prompts regeneration: "Your
prioritization is 30 days old. [Refresh your top 5 →]"

---

## PHASE 11 — Compliance Framework Selection Wizard (NEW)

A structured questionnaire that recommends the right compliance framework. Triggered
when the user first navigates to the compliance section, or manually from
Settings > Compliance.

### The Decision Tree

The wizard asks 8 questions:

```
1. What industry does the company operate in?
   [SaaS / FinTech / Healthcare / E-Commerce / Enterprise Software / Government / Other]

2. Who are the primary customers?
   [Consumers / SMB / Enterprise / Government / Healthcare orgs / Financial institutions]

3. Does the company handle payment card data?
   [Yes — we process payments / Yes — we store card data / No / Not sure]

4. Does the company handle health or medical information?
   [Yes / No / Not sure]

5. Do any customers require a specific compliance attestation as a contract condition?
   [SOC 2 / ISO 27001 / PCI-DSS / HIPAA BAA / FedRAMP / No / Not sure]

6. Does the company have investors or a board asking about compliance?
   [Yes, SOC 2 specifically / Yes, but not specific / No / Not sure]

7. Does the company sell to US federal government or handle government data?
   [Yes / No / Not sure]

8. What is the company's realistic timeline for initial compliance?
   [3–6 months / 6–12 months / 12–18 months / No timeline set]
```

### Output

A ranked recommendation (top 2 frameworks) with:
- Which framework and why (2–3 sentences, business-language rationale)
- An honest assessment of what achieving it requires: rough effort estimate (engineer
  months), major milestones, common blockers
- A gap analysis against the current KB: "Based on what I know about your stack, here
  are the biggest gaps between where you are and [framework] readiness"
- The recommendation is stored as a decision log entry (kind: `design_choice`,
  title: "Compliance framework selection")

---

## PHASE 12 — 90-Day Plan Generator (NEW)

A milestone-driven task list produced during or immediately after onboarding. Visible
on the home dashboard. Tasks surface in the morning digest.

### Generation

Generated by Claude using: intake answers, org profile, entity graph state, and
compliance targets. The plan is organized by week (Week 1 through Week 13) with
3–5 tasks per week.

Tasks are contextualized to the specific company. Not "Week 1: meet your team" —
"Week 1: schedule 1:1s with the Platform Engineering and Mobile teams (the two teams
that own your highest-risk services based on what you've told me)."

### Task Structure

Each task has:
- Week number
- Title (short, action-oriented: verb + object)
- Description (2–3 sentences of context)
- Why it matters (one sentence)
- Done condition (specific and testable: "threat model exists for Payments API with
  at least 5 STRIDE findings recorded")
- Source tag: intake / kb_state / compliance / manual

### Adaptivity

As the KB grows, Tank identifies completed tasks automatically where possible (e.g.,
"Generate threat model for [service]" → marks done when a threat model for that service
exists). For tasks that can't be auto-detected, the user checks them off manually.

The plan regenerates on demand. Monthly nudge: "Your 90-day plan has [N] uncompleted
items this week. [Review →]"

### Home Dashboard Integration

Show the current week's tasks on the home dashboard as a "This week" card. Not the
full plan — just this week's 3–5 items. Link to the full plan view.

---

## PHASE 13 — Navigation & Information Architecture

### Left Navigation Structure

```
Home (dashboard)
─────────────────
Discover
  └── Intake Interview
  └── Org Discovery
  └── Security Stack Audit
─────────────────
Analyze
  └── Chat
  └── Threat Models (DFD)
  └── Design Reviews
─────────────────
Track
  └── Risk Register
  └── Decisions Log
  └── Vulnerabilities
  └── Findings
─────────────────
Build
  └── Policies
  └── IR Runbooks
  └── Workstreams
  └── 90-Day Plan
─────────────────
Report
  └── Reports
  └── Program Dashboard
  └── Compliance
─────────────────
Knowledge
  └── Entity Graph
  └── Lessons DB
  └── Glossary
─────────────────
/me (Ownership Dashboard)
Settings
```

The groupings — Discover, Analyze, Track, Build, Report — map directly to the
first hire's job during the first 90 days and reinforce the structured journey framing.

### Home Dashboard

The home dashboard is never empty after onboarding. It always shows:

- **Program stage indicator** (top, prominent): which tenure phase the user is in
  (Discovery / Assessment / Foundation / Program) with days elapsed and a "Stage
  checklist" link
- **This week's tasks** (from 90-Day Plan, if generated): 3–5 items for the current week
- **Morning digest summary**: last generated digest, with "Regenerate" link
- **Top 3 priorities** (from Prioritization Engine, if generated): shown as cards with
  "done" condition visible
- **Recent decisions** (last 3 from Decisions Log): shown as a compact strip
- **KB health indicator**: chunk count, entity count, last ingestion date — with a
  "Build KB" CTA if counts are low
- **Incomplete setup prompts** (if applicable, shown as non-blocking banners):
  intake interview incomplete / stack audit incomplete / no threat models yet

### Tenure-Aware Lens

The existing Map → Prioritize → Execute → Maintain phases are retained. The redesign
makes them more concrete:
- Lean into the phase framing harder in nav labels, empty states, and nudge copy
- Each phase has a checklist (surfaced on click from the program stage indicator)
- Phase transition is manual — the user clicks "I'm ready to move to Assessment" when
  they feel Discovery is complete. Tank surfaces the checklist to help them judge.

---

## PHASE 14 — README Rewrite

After all phases are complete, rewrite `README.md` completely.

The new README speaks directly to the first security hire. Tone: direct, confident,
written for a senior engineer who does not need hand-holding but does need a clear
tool that respects their time.

### Structure

**Opening (no header — just the statement):**
> You just got hired as the first security engineer at your company.
> Nobody has done this before. There is no security program. Here is how Tank helps
> you figure out where to start.

**What Tank does (one section):**
Not a feature list. A narrative: "On Day 1, Tank asks you 20 questions. You don't need
any documents. By the end, you have a starting point: a skeleton of your company's
services and risks, a list of who to meet, and a brief you can share with your manager.
Over the next 90 days, Tank helps you build the rest."

**What Tank helps you build over 90 days (one section):**
- Days 1–14: discovery — what exists, who owns it, where the risks are
- Days 15–45: assessment — threat models, risk register, prioritized top 5
- Days 30–60: foundation — policies, runbooks, vulnerability management
- Days 60–90: program — metrics, leadership reports, making it all repeatable

**How to get started (minimal setup instructions):**
Accurate, current, minimal. Just what's needed to run Tank locally or access the
hosted version.

**What Tank is not:**
> Tank is a force multiplier for a security engineer who knows what they're doing.
> It does not replace expertise, make risk decisions for you, or guarantee compliance.
> It gives you structure, starting points, and context so you can do the work faster
> and with more confidence.

---

## General Constraints

- Single-user application. Stub `user_id` on new entities for future multi-user support
  but do not enforce it.
- Do not delete any existing feature code. Features with no verdict change (KEEP) are
  wired in as-is. Retired features (none in this redesign — all features are KEEP or
  KEEP & EVOLVE) would be commented out, not deleted.
- Every Claude API call must include org profile (company name, industry, team size,
  compliance targets) as baseline system prompt context once intake is complete.
- Response caching: any Claude call with identical inputs must return a cached result.
  Cache keyed on hash of inputs.
- Graceful empty states everywhere: no feature should show a blank page or empty table
  as its first impression. Every empty state has a CTA pointing to the action that fills it.
- Write a summary comment at the top of every file significantly modified.
- After each phase, run the app and smoke test before continuing.
- If a decision requires a product call, choose the conservative option and leave a
  `// TODO: product decision —` comment.

---

## Execution Order

Follow this exactly. Phases 2–4 are Phase 1 of the build order from the evaluation —
they are the minimum viable redesign and must ship together before anything else.

```
Phase 0   — Pre-build audit and plan (no code)
Phase 1   — Data model and migrations
Phase 2   — Quick-start intake interview  ← SHIP THIS FIRST
Phase 3   — Onboarding flow revision      ← SHIP WITH PHASE 2
Phase 4   — Chat empty-KB mode            ← SHIP WITH PHASE 2
Phase 5   — Org discovery wizard
Phase 6   — Security stack audit template
Phase 7   — KEEP & EVOLVE features (in order listed)
Phase 8   — Security policy scaffolding
Phase 9   — Vulnerability management workflow
Phase 10  — Prioritization engine
Phase 11  — Compliance framework selection wizard
Phase 12  — 90-day plan generator
Phase 13  — Navigation and information architecture
Phase 14  — README rewrite
```

Do not start Phase 5 until Phases 2–4 are complete and smoke tested.
Phases 2, 3, and 4 must ship together — they are one atomic change.

---

## Final Smoke Test

Run this end-to-end after all phases are complete:

1.  Create a new user with no existing data. Confirm the intake interview launches
    automatically before the dashboard is shown.
2.  Complete all 20 intake questions. Confirm entity stubs are created for named
    services, teams, and tools. Confirm a Day-1 Brief is generated without any
    uploaded documents.
3.  Open the chat immediately after intake with no documents ingested. Confirm
    discovery mode is active (badge visible), responses acknowledge KB sparseness,
    and provisional entity capture chips appear when new entities are mentioned.
4.  Run the Org Discovery Wizard: connect a GitHub token, scan repos, import a
    small CSV team directory, manually add one service. Confirm all produce entity
    stubs correctly.
5.  Complete the Security Stack Audit for at least 8 categories. Confirm it appears
    on the program dashboard.
6.  Ingest one document. Confirm KB chunk count increases and chat discovery mode
    badge updates.
7.  Generate a threat model for one service entity. Confirm findings feed into
    the risk register via the post-generation prompt.
8.  Run the Prioritization Engine. Confirm it produces a concrete top-5 with
    rationale and done conditions — not a sorted list.
9.  Run the Compliance Selection Wizard. Confirm it produces a recommendation with
    honest effort assessment and creates a decision log entry.
10. Generate the 90-Day Plan. Confirm it references the company's specific services
    and teams from the entity graph.
11. Generate a State of Security report. Confirm it reads as business language
    readable by a non-security executive.
12. Generate one security policy. Confirm it uses the company's actual service names
    and creates draft decision log entries.
13. Add a CVE to the vulnerability triage queue. Confirm the triage → assign → close
    workflow works and integrates with the program dashboard stats.
14. Open the home dashboard. Confirm it shows program stage, this week's plan tasks,
    top 3 priorities, and recent decisions — none of them blank.
15. Check all five left navigation groups (Discover, Analyze, Track, Build, Report).
    Confirm every section has a non-empty state or a meaningful CTA.
16. Read the new README. Confirm it addresses the first security hire directly and
    does not read like a generic tool description.
