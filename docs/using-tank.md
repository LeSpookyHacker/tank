# Using Tank — day-to-day workflows

The reference docs cover what each feature does. This file is about
**how you actually use Tank** over a week / month / year. It maps
the daily rhythms a Sr/Staff/Mgr security engineer has to specific
Tank surfaces.

---

## Morning routine (5 min)

1. Open Tank (your tunnel + `http://localhost:8000` if on a dev VM).
2. **Today dashboard** loads. Read top-down:
   - **Greeting + lens** — Tank tells you which tenure mode you're
     in (Map / Prioritize / Execute / Maintain).
   - **Today's digest** — up to 5 nudge cards (coverage gaps,
     architecture drift, expiring decisions, abandoned threads).
     Each is one-click dismiss / snooze / act.
   - **Today's briefs** — meeting prep generated overnight for any
     calendar events with known attendees.
   - **Follow-ups due today** — items you tracked yesterday.
   - **Hot entities (7d)** — services you've been touching most.
3. Pick the **one thing** from the digest and act on it. Everything
   else can wait.

> ⬜ **Screenshot placeholder**: morning digest with 3 nudges active.
>
> ![Morning digest](images/workflow-morning-digest.png)

---

## Before a meeting (2 min)

If you have a 1:1 with someone in your KB:

```
/meeting-prep → enter their name (or click the link in Today's briefs)
```

You get a one-screen brief:

- **Who they are** — role, team, where they sit in the org.
- **Their world** — services they own, what's hot right now.
- **Your overlap** — what you should care about together.
- **Unknowns** — things Tank doesn't know and you should ask.
- **Ranked questions** — 5 questions with reasoning, ordered by
  leverage.
- **One thing to offer** — something Tank thinks you uniquely have
  to bring.

After the meeting, click "Capture notes" → freewrite → Tank extracts
proposed entity updates via the notes-to-KB diff. Confirm what's
real; the rest gets dropped.

---

## Authoring a design review (10-30 min)

```
/design-reviews → "+ new review"
```

Drop your title + a freewrite of the proposal. Tank's intake helper
runs Sonnet over your freewrite and seeds:

- **Scope summary** (2-3 sentences echoing what you wrote).
- **Likely risk areas** (3-6 phrases — specific, not generic).
- **Missing info** (questions the reviewer should demand).
- **Suggested reviewers** (names from your KB).
- **Checklist** — 6-10 items keyed to the design across:
  AuthN / AuthZ / Crypto / Data classification / Third-party deps /
  Blast radius / Logging / Threat-model touch-points / Rollout.

Work through the checklist; each item has a notes field. Status
moves intake → reviewing → approved/rejected.

**On approve**: spawn a decision from the review. The decisions row
gets `source='design_review'` and links back. This is how Tank
builds your decisions log over time without you having to remember
to log things manually.

> ⬜ **Screenshot placeholder**: design review checklist mid-review.
>
> ![Design review](images/workflow-design-review.png)

---

## During / after an incident (15-60 min)

While paged or right after:

```
/postmortems → "+ new postmortem"
```

Freewrite what happened. Don't worry about structure. Sonnet drafts:

- Summary (plain-English for non-engineers)
- Timeline (one bullet per event)
- What failed (proximate cause)
- Why (mechanism)
- Contributing factors
- Mitigations applied during the incident
- Action items (each will become a follow-up)
- Services affected (linked to entity IDs)
- Severity guess (sev1/2/3)

Edit before publishing. **On publish**:

- Each action item → row in `followups` you can assign owners to.
- Each service-affected → linked to its entity.
- Sonnet extracts 1-4 **lessons** that go into `/lessons` (your
  team's queryable lessons-learned DB).

A week later, ask in chat: *"have we hit anything like an Okta SCIM
race condition before?"* and Sonnet's `search_lessons` tool pulls
your past postmortems by tag.

---

## When architecture changes

After ingesting a new arch doc or re-summarizing a repo:

```
Today dashboard → "architecture_drift" nudge appears
```

Click through to the affected service. Click "Regenerate against
current arch." Tank's threat-model generator runs with the prior
TM in context and tags each prior threat as:

- `still_valid` — keep
- `updated` — refine description; same threat, evolved
- `invalidated` — remove (e.g. integration was deleted)
- `new` — genuinely new

You get TM v2; v1 stays in the version history. The decisions log
gets cross-linked to anything you carry over.

> ⬜ **Screenshot placeholder**: threat model with state badges.
>
> ![Threat model v2](images/workflow-tm-v2.png)

---

## Friday afternoon (10 min)

At 16:00 on your reflection day:

1. **Weekly reflection** trigger fires. Open the digest.
2. Run the **weekly security digest** report (auto-subscribed on
   Day-14). Tank summarizes:
   - New / changed entities this week
   - Decisions made
   - Threat models updated
   - Postmortems published
   - Coverage gaps spotted
3. Optionally write a one-line journal entry. The evening journal
   prompt fires at 18:00 if you haven't.

---

## Once a month

- **Check `/me`** — your owned-entities risk scores. Anything red?
  Anything that drifted?
- **Run `attack_mapping`** — see which MITRE techniques map to your
  services' threats and where detections are missing.
- **Review `/compliance`** — control evidence map. Any controls
  with no evidence? Either ingest evidence or flag the gap.
- **Glossary review** — `/glossary` shows new candidate terms
  Tank extracted. Confirm / reject. The confirmed glossary enriches
  future chat replies.

---

## Anniversary milestones (Day 30/60/90/180/365)

Tank fires **two** retro reports automatically:

- A **generic anniversary retro** ("what you built, learned, drifted,
  next 30 days").
- A **security-focused retro** with the same shape but keyed to:
  threats added/closed, decisions made, controls covered, detections
  added, incidents handled.

At Day 30, the **philosophy doc** gets seeded from your first month
of decisions + tabletops. At Day 60/90/180/365, Tank suggests
evolutions ("you've taken these 3 new stances since the last update;
add them?").

> ⬜ **Screenshot placeholder**: anniversary retro at Day-60.
>
> ![Anniversary retro](images/workflow-anniversary.png)

---

## Threat modeling a service with DFD (30-60 min, per service)

```
Sidebar → Pipeline → DFD Analysis → "+ New analysis"
```

**Stage 1 — get your diagram in.** Four ways:

| Tab | When to use |
| --- | --- |
| Paste Mermaid | You have a `.mmd` file or are comfortable writing Mermaid source |
| Upload file | Drag-drop a `.mmd`, `.png`, or `.jpg` — images go to Claude Vision |
| From document | Upload an architecture PDF or DOCX — Claude extracts the data flow |
| From description | Paste a plain-English description — Claude generates Mermaid for you |

Click "Load example" on Tab A to get a reference DFD to start from.
The sample data pack includes four ready-to-use `.mmd` files in
`sample_data/dfd/` (payments-api, identity-svc, pii-vault, webhook-router).

**Stage 2 — SSE progress tracker.** Four steps: parsing diagram →
identifying components → mapping attack surfaces → generating threat
model. Typically 20-40 seconds.

**Stage 3 — interactive workspace.** Split-panel layout:

- **Left (diagram)**: Mermaid rendered with severity `style` directives.
  Click a node to filter threats to that element. Hover for element name
  + threat count. Zoom with `+`/`−` or scroll wheel.
- **Right (findings)**: Severity summary strip at top. Each threat card
  shows title, CVSS estimate, STRIDE category, element, description,
  collapsible mitigation, and OWASP/CWE reference pills. Use the filter
  pills to focus on Critical/High only or a single STRIDE category.
  Click "Highlight in diagram →" to cross-link a card to its node.

**Cache**: results are SHA-256 cached — revisiting the same diagram
loads instantly. The ⚡ badge confirms a cache hit. Click "↺ Run again"
to force a fresh STRIDE pass.

**Improve diagram**: if the auto-generated Mermaid is missing trust
boundaries or services Tank knows about, click "Improve diagram" — Tank
uses your KB to add missing context.

**Exports:**

- **Print / Save as PDF** — professional print layout with cover page,
  full diagram SVG, threat table, STRIDE 6×4 coverage matrix, Mermaid appendix.
- **Annotated `.mmd`** — Mermaid source with `style` directives showing severity.
- **Original `.mmd`** — unmodified input.
- **JSON** — metadata + elements + full threat objects (CVSS, references, etc.)

---

## Running a tabletop (60-90 min, periodic)

```
/tabletops → "+ new tabletop" → pick service + threat
```

Tank generates:

- 1-paragraph scenario (read aloud to start the exercise)
- 4-6 timed injects (each is a new event the facilitator reads at
  T+5min, T+10min, etc.)
- Facilitation notes
- Evaluation rubric (4-7 observables)

Run with your team. After:

```
On the tabletop page → "Capture lessons" → bullet list + tags
```

Each bullet becomes a lesson; tags make them retrievable.

After running a tabletop, a collapsible "Generate IR runbook from
this scenario" section lets you produce a full 5-phase incident-response
runbook pre-populated with the tabletop's service and threat kind —
no re-typing required.

---

## Tracking a risk (formal risk register)

When you identify a risk that needs ongoing tracking (not just a one-off
decision), add it to the risk register:

```
/risks → "Add risk"
```

Fill in title, category (data_breach / availability / supply_chain / …),
inherent likelihood (1-5) and impact (1-5). Tank immediately queues a
background KB assessment — Sonnet pulls the service card, threat model,
and existing decisions and computes:

- **Residual likelihood + impact** (after existing controls)
- **Recommended treatment** (mitigate / accept / transfer / avoid)
- **Control gaps** — controls Sonnet expected but didn't find in the KB
- **Suggested next steps**

Heat colors on the list page: **Critical** (score ≥ 20), **High** (≥ 12),
**Medium** (≥ 6), **Low** (< 6).

Assessments set a 90-day review deadline; the `risk_review_due` nudge
appears on the Today dashboard when a deadline passes. Click "Re-assess
with KB" on the detail page to refresh after ingesting new controls docs.

In chat, ask: *"What are our top residual risks?"* or *"Which access_control
risks are we accepting?"* — Tank uses the `get_risk_register` tool.

---

## Viewing the security program dashboard

```
/security-program
```

Six metric domains render instantly (no Claude call):

| Domain | What you see |
| --- | --- |
| Threat models | Total / drifted / updated in 30 days |
| Vulnerabilities | Open by severity + average age |
| Risk register | Open risks / overdue reviews |
| Compliance | Controls with evidence vs. without |
| Incidents | Postmortems (90d) / open followups |
| Design reviews | Open / approved (90d) |

**12-week trend**: the Sunday 09:30 scheduler job saves a snapshot; the
trend table below the cards shows your posture over the past 3 months.

**Executive brief**: click "Generate executive brief" for a Sonnet-written
1-page summary (green / yellow / red health indicator, key achievements,
top risks, recommended priorities) suitable for a board or exec-team update.
Copy the rendered Markdown directly into a slide or doc.

---

## Generating an IR runbook

After a tabletop, postmortem, or whenever you want a written playbook:

```
/ir-runbooks → fill in service + threat scenario + severity
```

Tank queries your KB for the service architecture, latest threat model,
recent postmortems, and relevant detections, then Sonnet generates a
5-phase playbook:

🔍 **Detect** — signals, alert queries, correlation steps  
🛑 **Contain** — immediate steps with time-box and decision points  
🧹 **Eradicate** — root-cause removal + success criteria  
♻️ **Recover** — restoration, validation, rollback decision points  
📢 **Comms** — stakeholder notification template + escalation path  

Generation takes 20-60 seconds. After reviewing, click **Confirm** to
mark it validated — unconfirmed runbooks show a warning badge. Use
**Print / Save as PDF** for an offline-ready incident binder.

Nudge surfacing: when a postmortem is published, Tank checks whether
each affected service already has a runbook. Missing ones appear as a
`missing_ir_runbook` nudge on Today so nothing falls through the cracks.

---

## Working with projects

Tank lets you compartmentalise your KB, threat models, conversations, and reports by
project — useful when you cover multiple teams, products, or engagements.

**Dashboard**: navigate to `/projects` to see a card grid of all projects. Each card
shows the project's color accent, icon, name, and description. The last project you
opened is sorted first (stored in `localStorage`).

**Creating a project**: click "New project" → pick an emoji icon, a color (native
browser color picker), add a name and optional description → Create.

**Opening a project**: click "Open →" on any card. The detail page shows:
- A color-accented header with the project's icon and name.
- A **Notes** section (only shown if notes are non-empty) — write anything Claude should
  keep in mind for this project: scope, priorities, team contacts, constraints.
- Scoped metrics: document count, conversation count, report count for this project only.
- Recent documents and conversations belonging to this project.

**Editing a project**: click "Edit" on the detail page to reveal an inline form. You can
update the name, description, icon, color, and notes without leaving the page.

**Project notes in chat**: notes you add to a project are automatically included in the
system prompt for conversations that belong to that project. The global side panel chat
(accessible from every page) does **not** inject project notes — it's intentionally
context-free.

**Switching active project**: from the dashboard, click "Switch to" on any card, or use
the project switcher dropdown in the top nav. The active project determines which project
newly ingested documents, conversations, and reports are assigned to.

**Data isolation**: each project's documents, conversations, threat models, design reviews,
postmortems, and reports are scoped by `project_id`. Counts and recent-items on the detail
page are always project-specific.

---

## Asking Tank a question (anytime)

Tank's chat is available two ways:

- **Side panel** (default) — a persistent panel on the right of every page.
  Click ✕ to collapse it to a "Chat ▰" pill at the bottom-right; click the
  pill to reopen. Drag the left edge to resize. The conversation persists
  across page navigation. Click "⤢" in the panel header to pop into the
  full-screen chat with that same conversation.
- **Full-screen** (`/chat`) — dedicated chat page; the side panel is
  suppressed here.

Tank has 15 tools:

- `search_kb(query)` — hybrid retrieval over your KB
- `get_entity(type, name)` / `list_entities(type)` — graph access
- `list_relationships(entity_id, direction)` — edges
- `find_control_gaps(control)` — services missing a control
- `get_threat_model(service)` — pull latest TM
- `find_decisions(kind?, status?, scope_entity_id?)` — query the log
- `get_recent_decisions(days)` — "what's been decided lately"
- `find_detection_for_technique(attack_id)` — coverage check
- `find_iam_risks(limit)` — top risky IAM policies
- `find_evidence_for_control(control_id)` — compliance lookup
- `search_lessons(query, tag?)` — past learnings
- `get_document(doc_id)` — fetch a specific doc
- `get_risk_register(category?, treatment?)` — open risks by residual score
- `find_ir_runbooks(service_name?, service_id?)` — IR runbooks for a service

You don't pick the tool — Sonnet does. Sample questions Tank handles
well:

- "What's the blast radius if payments-api gets owned?"
- "Why did we decide to keep webhook signing optional?"
- "Do we detect lateral movement from staging to prod?"
- "What controls is identity-svc missing?"
- "Has anything like the Vault sidecar outage happened before?"
- "Who should I talk to about the deprecation of orders-api?"

Every answer carries citations (clickable to source chunks) and a
provenance badge (source / inferred / claim).

> ⬜ **Screenshot placeholder**: chat with tool-use trace expanded.
>
> ![Chat with tool use](images/workflow-chat-tools.png)
