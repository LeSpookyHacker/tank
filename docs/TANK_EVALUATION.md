# Tank — Strategic Evaluation & Redesign Planning Report

*Generated: 2026-05-28*

---

## Section 1: Executive Summary

Tank today is a powerful tool for a specific kind of person in a specific kind of situation: a senior or staff security engineer who joins a company that already has security infrastructure in place — existing services, some architecture documentation, a known attack surface, maybe some compliance requirements already in flight. For that person, Tank is excellent. They ingest what exists, build a knowledge graph from it, and use Tank as a force multiplier to chat over documents, generate threat models, track decisions, and run a daily-companion cadence that keeps them oriented and productive.

The problem is that person is not the target anymore. The new target is the first security hire — someone who joins a company where nothing security-related exists yet. No policies. No asset inventory. No threat models. No compliance baseline. Possibly no documentation of any kind. They need to simultaneously discover what the company has built, assess its risk, start building foundational security infrastructure from scratch, and convince leadership and engineering that all of this matters — all within 90 days, alone, with no security budget and no team. This is one of the most disorienting roles in the industry, and it is vastly more common than the staff-engineer-joins-mature-org scenario Tank was designed for.

The gap between these two personas is not primarily a feature gap. Tank has most of what the first hire needs — threat modeling, risk register, decisions log, IR runbooks, program dashboard, compliance mapping, daily companion. The gap is a philosophy gap. Tank currently *amplifies* an existing signal: you bring it documents, it makes them queryable. The first hire has no documents to bring. Tank needs to be able to *generate* the signal from nothing — from a structured intake interview, from conversations with engineers, from a GitHub org scan, from answers to twenty direct questions on Day 1. Until Tank can be genuinely useful before the first document is ingested, it cannot serve this persona at all.

Three things need to change fundamentally. First, bootstrapping: Tank must provide value from the moment someone opens it, with no pre-existing KB. This means a zero-doc intake flow, a chat experience that works in discovery mode, and an entity graph that can be seeded from answers to questions, not just from uploaded files. Second, prioritization: the first hire will accumulate dozens of findings across fifteen systems with no budget and no team. Tank currently has a risk register but no way to answer "out of all of this, what do I actually fix first?" That answer has to account for data exposure, regulatory risk, exploitability, and business context — not just CVSS scores. Third, communication: the first hire spends enormous energy translating technical findings into business language for leadership. Tank produces detailed technical artifacts but has no leadership-communication layer. A first hire needs to walk into a board meeting with a two-page "State of Security" brief, not a 40-item risk register.

What does *not* need to change: the privacy contract, the knowledge graph model, the tenure-aware lens, and the daily companion cadence. These are exactly right for this persona. The first hire absolutely needs a privacy-preserving tool (they're handling their employer's sensitive architecture from Day 1), a living knowledge graph (they're building one from nothing), a lens that evolves from discovery to execution over 90 days (that is literally their job), and a daily companion that surfaces what's decayed, what needs follow-up, and what they're forgetting. The foundation is correct. The missing pieces are the front door and the output layer.

---

## Section 2: Current Feature Verdict Table

| Feature | Current State | Verdict | Rationale |
|---|---|---|---|
| Document Ingestion | Parses PDF, DOCX, MD, CSV, JSON, YAML, PNG, Git repos into a typed KB | KEEP & EVOLVE | Core pipeline is solid. Needs: org-discovery connectors (GitHub org scan, directory import), auto-discovery of what *can* be ingested, and graceful handling of the empty-KB first session. Zero-doc fallback is the critical gap. |
| Chat with KB | Streaming chat with 15 tools; retrieves chunks + entity cards; handles tool use loops | KEEP & EVOLVE | The highest-value feature, and it's nearly useless on Day 1 with an empty KB. Needs a "discovery mode" that provides value even with no documents — guided questions, scaffolding suggestions, and first-hire-specific prompting when context is sparse. |
| Entity Graph | 14 entity types, 9 relationship kinds; provenance tracking; graph visualization | KEEP & EVOLVE | Outstanding once populated, useless until it is. Needs a seeding path: intake interview answers should create entity stubs. The first hire should be able to say "we use AWS, Postgres, and Okta" and have those entities appear without uploading anything. |
| Reports (11 kinds) | Threat landscape, cross-service gaps, 30/60/90 plan, stakeholder map, questions for team, control matrix, oncall handoff, weekly digest, attack mapping, IAM audit, risk register | KEEP & EVOLVE | Most reports require a populated KB to produce anything useful. Immediate need: a leadership-communication layer — business-language summaries of findings, not just technical catalogs. Add "State of Security" and "Initial Assessment" as first-class report kinds. |
| DFD Threat Modeling | 4-mode input, SSE progress, split-panel workspace, STRIDE + CVSS, PDF export | KEEP & EVOLVE | Professional-grade feature. First hire will reach for this from Day 14 onward as they learn what services exist. Minor adaptation needed: "discovery mode" for diagrams built from partial knowledge (should explicitly mark assumptions as assumptions). |
| Living Threat Models | Per-service versioned TMs with drift detection; confirms/invalidates prior threats | KEEP | Exactly right for this persona. The first hire generates threat models for each critical service and re-runs them as they learn more. Drift detection is especially valuable when they're still discovering what exists. No changes needed. |
| Decisions Log | Design choices, accepted risks, deferred fixes, security invariants; expiry + reaffirmation | KEEP & EVOLVE | Even more critical for the first hire than for a mature-org engineer. Every founding decision — which compliance framework to pursue, which WAF to adopt, which risks to accept — needs to be on record. Should be more prominent in the UX for early-tenure users, not buried in the sidebar. |
| Design Reviews | Intake → checklist → approve/reject → spawn decisions | KEEP & EVOLVE | First hire needs to *establish* this process, not just use it. Tank should help them introduce design reviews to an engineering org that has never done them — starter templates for how to pitch the process, lightweight intake forms, approval thresholds scaled to team size. |
| Security Workstreams (postmortems, tabletops) | Draft from freewrite; auto-spawn followups + lessons; tabletop scenario + injects | KEEP & EVOLVE | First hire may face incidents before IR infrastructure exists. The postmortem workflow is excellent for this — it structures a retrospective from a freewrite, which is exactly how an unprepared-but-learning first hire documents an incident. Tabletops are a Day 60–90 priority for testing readiness. |
| Coverage & Visibility (Sigma/IAM/compliance) | Sigma ingestion, IAM risk audit, compliance evidence mapping, ATT&CK coverage, attack-surface snapshots | KEEP & EVOLVE | The first hire's Days 14–30 are largely about discovering what controls exist (answer: probably almost none). This feature set is perfect for that task but requires the relevant documents to be ingested first. Needs a "here's what we found, here's what's missing" summary that surfaces gaps even from a sparse KB. |
| Risk Register | Inherent/residual L×I scoring, treatment, 90-day review scheduling | KEEP | Exactly right for the first hire. They will accumulate a risk register that grows from 5 items to 50 over 90 days. The scoring model and treatment tracking are appropriate. The missing piece — addressed in the gap analysis — is a prioritization engine that translates the register into "here's your top 5 this quarter." |
| Security Program Dashboard | 6-domain KPI aggregation, on-demand exec brief, 12-week trends | KEEP & EVOLVE | Designed for measuring a program that exists. For the first hire, everything is red on Day 1, and that's expected, not alarming. Needs a "building from zero" mode that shows trajectory and intent — "here's where we started, here's where we are, here's the roadmap" — not just current state. |
| IR Runbooks | Per-service, per-scenario 5-phase playbooks; Sonnet-generated; IR-tabletop integration | KEEP & EVOLVE | Generator is the right abstraction. First hire often creates all runbooks from nothing in the Foundation phase. Current generation requires a service entity to exist and a threat scenario to be named. This works well once the first hire has done basic discovery — prioritize generating the "ransomware" and "data breach" runbooks before anything else. |
| Partner Mode (digest, journal, nudges, meeting prep) | Morning digest, pre-meeting briefs, evening journal prompt, Friday reflection | KEEP & EVOLVE | The daily companion cadence is one of Tank's most important differentiators and it is correctly structured for this persona. Needs first-hire-specific nudge kinds: "You haven't met with [team] yet," "Week 1 check: have you identified your highest-risk service?", "Day 30 milestone: threat model for your top service is due." |
| Day-1 Brief | Sonnet-generated new-hire brief from role + scope; lists top entities, week-1 questions, readings, suggested meetings | KEEP & EVOLVE | Currently requires at least some KB context to produce a useful brief. Needs to work from the intake interview alone — before any document is uploaded. A Day-1 brief generated from twenty intake questions is better than no Day-1 brief at all. |
| Anniversary Retros | Security-focused retrospectives at Day 30/60/90/180/365 | KEEP | Perfectly aligned with the first hire's milestone structure. The Day 30, 60, and 90 retros map directly to the Discovery, Assessment, and Foundation phases. No changes needed beyond the broader KB bootstrapping work. |
| Tenure-Aware Lens | Map → Prioritize → Execute → Maintain based on tenure_started_at | KEEP | This feature was designed for the first hire even if Tank wasn't explicitly targeting them. The four phases — Map, Prioritize, Execute, Maintain — are a precise description of the first security hire's journey. Do not change this; lean into it harder. |
| Lessons DB | Lessons extracted from postmortems, design reviews, tabletops; tagged, searchable | KEEP | The first hire especially needs systematic learning capture. They'll make mistakes and encounter novel situations constantly. A searchable lessons DB that compounds over 90 days becomes one of their most valuable artifacts. |
| Glossary Builder | Discovers company-specific jargon; user confirms candidates | KEEP | Genuinely useful; the first hire is learning an entirely new company's vocabulary. Reduce its UX prominence for Days 1–30 — it's not a priority when there's nothing in the KB — but keep it as background enrichment once the KB fills. |
| Security Philosophy Doc | Seeded at Day 30, evolved at Day 60/90/180/365 | KEEP | Correctly timed already. The first hire shouldn't be thinking about their personal security philosophy on Day 1 — they should be discovering what exists. By Day 30 they've formed enough opinions for this to be useful. |
| Ownership Dashboard (/me) | Claimed service entities with risk scores weighted by TM drift, threats, decisions, postmortems | KEEP & EVOLVE | The first hire owns everything, and tracking that ownership explicitly is important for personal accountability. Needs adaptation: on Day 1 there's nothing to own and no risk score to compute. Should guide the user toward claiming ownership of services as they discover them, not present an empty table. |
| Onboarding Flow | 5-step intake: role, scope freewrite, internal TLD, digest time, Day-1 brief | KEEP & EVOLVE | Needs a major revision. The current onboarding configures a companion for someone who already knows their context. The new onboarding should conduct a structured discovery interview — "What does the company build? Who are the customers? What data do they handle? What cloud providers? Any existing security controls?" — and bootstrap the KB from those answers. Configuration of digest time and TLD can come after. |
| Projects | Scoped workspaces with doc/conversation/report segregation; color, notes, team linkage | KEEP & EVOLVE | First hire creates all projects from scratch and may not know what projects *should* exist. Needs starter project templates: "Core Infrastructure," "Customer-Facing Services," "Internal Tools," "Compliance & Governance." A first hire should be able to click "start with suggested projects" on Day 1. |
| Entity Browser | Filterable list by type; relationship graph visualization; ownership claim | KEEP & EVOLVE | Correct feature, wrong first impression. On Day 1 with an empty KB, this page shows nothing. The empty state should guide the user to the intake interview or org discovery workflow, not just show a blank table. |
| Watchers (folder/ICS/CVE/GitHub) | Continuously monitors folders, calendars, CVE feeds, GitHub repos for changes | KEEP & EVOLVE | CVE feed and GitHub repo watcher are especially valuable for the first hire — CVEs immediately show which vulnerabilities apply to their stack, and GitHub repo watcher keeps the KB current as the codebase evolves. Add GitHub org-level discovery: scan the org, find all repos, suggest which ones to ingest. |
| Quick-Start Intake Interview | Does not exist | NEW | The highest-priority missing feature. Twenty structured questions about the company's tech stack, data sensitivity, cloud providers, team structure, compliance context, and known incidents. Answers seed the entity graph, generate an initial risk hypothesis, and produce a Day-1 brief — no documents required. |
| Org Discovery Wizard | Does not exist | NEW | Guided workflow to build an initial asset inventory from sources that don't require manually uploaded docs: GitHub org scan (list all repos, infer services), Confluence/Notion space list, team directory import (CSV or directory query), cloud provider inventory (if credentials are available). First hire shouldn't have to manually enter every service they discover. |
| Security Policy Scaffolding | Does not exist | NEW | The first hire will write the company's first security policies from scratch. Tank should generate starter versions of the five most critical policies — Acceptable Use, Incident Response, Secure Development Lifecycle, Vulnerability Management, Data Classification — anchored to the discovered KB (using the company's actual stack names, not generic placeholders). These aren't final policies; they're first drafts the first hire can own and edit. |
| Prioritization Engine | Does not exist | NEW | Given a risk register with 40 items across 15 systems and a budget of zero, what do you fix first? The answer must account for: data exposure (PII, financial, credentials), regulatory consequence, exploitability, likelihood of targeting, and existing compensating controls. Tank needs to surface "here's your top 5 for this quarter" as a concrete, opinionated recommendation — not just a sorted risk register. |
| Leadership Communication Templates | Does not exist | NEW | The first hire regularly needs to translate technical risk into business language for leadership, board, or investors. Tank should produce: State of Security (monthly, one page), Initial Assessment (what I found in the first 30 days), Program Roadmap (what we're building and why), and Risk Translation (for each high-severity finding: what this means if it's exploited, not just what the vulnerability is). |
| Compliance Framework Selection Wizard | Does not exist | NEW | The first hire at an early-stage company often doesn't know which compliance framework to pursue — or has vague leadership pressure toward "SOC 2" without understanding what that means. Tank should guide them through a decision tree based on: industry, customer type, data handled, geographic reach, and investor requirements. Output: a recommendation with rationale and an honest assessment of what achieving it will take. |

---

## Section 3: First-Hire Journey Map

### The Reality of Day 1

The first security hire walks in to a company that has been operating — sometimes for years — with no formal security function. Engineers have made security decisions ad hoc. Some are good. Many are not. The infrastructure is real, in production, handling real customer data. There is no documentation of what it is. There is no inventory of what data lives where. Nobody has ever run a threat model. The incident response plan, if it exists, is a Slack message from two years ago that says "call Bob if something breaks."

The engineer's first challenge is not to fix anything. It's to understand what exists well enough to know what's most dangerous. And they have to do this while simultaneously building credibility with an engineering org that may be skeptical, building a relationship with leadership that may have vague expectations, and producing enough visible output to justify the hire.

This is not a knowledge problem. It's an orientation problem. The first hire doesn't need more information — they need a structured way to gather it, evaluate it, and act on it. Tank's job is to be that structure.

---

### Phase: Discovery (Days 1–14)

**What they're trying to accomplish:**
Build a mental model of the company — what it builds, who the customers are, what data it handles, how the infrastructure works, who the engineering teams are and what they own, what third-party dependencies exist, and whether there are any existing security controls at all.

**Information they don't have:**
Everything. They may not know what cloud providers are in use, what the database stack is, whether there are API keys hardcoded anywhere, or who is responsible for infrastructure. They learn this from conversations, from reading Terraform configs, from scanning GitHub, from walking around and asking engineers direct questions.

**Decisions they need to make:**
Where to focus attention first. With finite time and no context yet, what do you prioritize learning about? Customer-facing services first? Anything handling payments or PII? Authentication systems? The answer depends on business model and risk profile, which they're still figuring out.

**Outputs they need to produce:**
- A rough asset inventory (even just a list of "services I know about")
- A "here's what I found in week 1" memo for their manager or CTO
- A prioritized list of who to meet and what to ask them
- An initial intuition about where the highest-risk areas are

**Where Tank inserts itself:**
Tank conducts the intake interview on Day 1, before any documents exist. Based on answers about the company's domain, stack, customer data, and team structure, it generates an initial entity graph (skeleton services, guessed dependencies) and a Day-1 brief. When the first hire meets an engineer and takes notes afterward, those notes go into Tank and become KB entries. Meeting prep before every 1:1 — "here's what I know about this person's team, here are the best questions to ask" — becomes the first hire's primary Tank interaction in week 1.

**Tank's biggest opportunity here:** Replace the blank page. On Day 1, the first hire doesn't know what to do first. Tank should tell them.

---

### Phase: Assessment (Days 15–45)

**What they're trying to accomplish:**
Take what they discovered and evaluate it rigorously. Which services are highest risk? Which vulnerabilities are present and which matter? What does the attack surface actually look like? What compliance frameworks apply to this company and what does meeting them require? What would a breach look like, and what would it cost?

**Information they don't have:**
No vulnerability history (no pentest, no bug bounty, no CVE triage). No threat model for any service. No compliance baseline — they may not even know which framework to pursue. No historical incident data.

**Decisions they need to make:**
Which compliance framework to target (often a business decision as much as a technical one). What "high risk" means in this company's context. Which risks to accept vs. address. How to rank 40 findings with no budget.

**Outputs they need to produce:**
- Initial risk assessment (must be readable by non-security leadership)
- Top 10 findings with business impact statements
- Compliance gap analysis with rough effort estimate
- A recommendation on which compliance framework to pursue and why

**Where Tank inserts itself:**
Threat modeling for the top 3–5 services identified during Discovery. Risk register population — every finding gets entered with category, inherent score, and treatment. Compliance framework selection wizard guides the decision. Initial Assessment report produces the leadership-ready summary that translates findings into business language ("this finding means a credential compromise could allow an attacker to exfiltrate your entire customer database; regulatory exposure is [X]").

**Tank's biggest opportunity here:** The prioritization engine. With 40 risk register entries and zero resources, "here's the ranked list" is the most valuable output Tank could produce. This does not exist today.

---

### Phase: Foundation (Days 30–60)

**What they're trying to accomplish:**
Start building the basics. The first hire now knows enough to act. They need to create foundational security infrastructure — not enterprise-grade, not perfect, but better than nothing and maintainable as the company grows. This phase is about policies, runbooks, and process.

**Information they don't have:**
They know what they need to build. What they lack are starting points. Writing a vulnerability management process from a blank page is slow; having a drafted process anchored to their specific stack that they can edit and own is fast. Most first hires underestimate how long good policy writing takes.

**Decisions they need to make:**
What "done" looks like for each foundational piece. An AUP that says "don't do bad things" is useless; one that's specific enough to be enforced is hard to write. How much process is appropriate for a 200-person company that moves fast? The first hire makes these calls alone, often without precedent.

**Outputs they need to produce:**
- First written policies (AUP, IR policy, SDL, vuln management, data classification)
- Basic IR runbook for the 2–3 most likely incident scenarios
- Vulnerability management process (how findings are triaged, tracked, and closed)
- A program dashboard showing where things stand — for their own sanity and for leadership

**Where Tank inserts itself:**
Security policy scaffolding generates first-draft policies anchored to the discovered KB. IR runbook generator produces service-specific playbooks. The program dashboard establishes a baseline — "this is where we started" — that will be meaningful at Day 90 when there's something to compare against. Risk register prioritization engine tells them what to address in the first sprint.

**Tank's biggest opportunity here:** Generating the starting points. A first draft they can edit is 10× faster than a blank page. Done well, the policies Tank generates should feel like they were written for this company, not downloaded from a template library.

---

### Phase: Program (Days 60–90 and Beyond)

**What they're trying to accomplish:**
Make everything repeatable and scalable. The first hire has done enough one-off work to understand the pattern. Now they need to systematize it — threat modeling as part of the dev lifecycle, security champions in engineering teams, metrics that show progress, a roadmap to present to leadership.

**Information they don't have:**
They don't have a clear picture of what progress looks like. Their gut says they've done a lot; leadership may not see it. They need metrics — not just technical ones, but business-language metrics that demonstrate that the investment in a security hire is paying off.

**Decisions they need to make:**
How to build relationships with engineering org (security champions program vs. embedded security vs. security guild). Which KPIs to track and report upward. What the 12-month security roadmap looks like and how to cost it for leadership.

**Outputs they need to produce:**
- Quarterly board/leadership brief on security program status
- Security program roadmap (12-month, business-language)
- Security champion program proposal
- KPI definitions and trend dashboard

**Where Tank inserts itself:**
Program dashboard with trend data — showing trajectory from Day 1 to Day 90 as a concrete story of progress. Anniversary retro at Day 90 synthesizes everything learned. Leadership communication templates produce the board brief. The decisions log (now 40+ entries) and lessons DB (now 10+ entries) are the receipts — evidence that the security program is being built deliberately, not reactively.

**Tank's biggest opportunity here:** The board brief. A first hire who can walk into a leadership meeting with a data-backed, business-language summary of security posture and roadmap — generated by Tank in 30 minutes from their KB — has a massive credibility advantage over one who shows up with a raw vulnerability list.

---

## Section 4: Feature Gap Analysis

Ranked by Value × Feasibility (High/High first, descending).

---

```
GAP: No zero-document starting point
JOURNEY PHASE: Discovery
CURRENT STATE: Tank requires at least some ingested documents before it can provide meaningful
value. Chat over an empty KB produces generic responses. The Day-1 brief requires ingested
content to synthesize. The entity graph starts empty. On Day 1 with no documents, Tank is
essentially a blank screen.
WHAT'S MISSING: A structured intake interview that asks the first hire ~20 direct questions
about their company — what it builds, who the customers are, what data is handled, what cloud
providers and key systems are in use, whether any security controls exist — and uses those
answers alone to produce a skeleton KB, an initial risk hypothesis, and a Day-1 brief.
PROPOSED FEATURE: Quick-Start Intake Interview. A guided 10–15 minute conversation (in chat or
a dedicated flow) that asks structured questions and, when complete, seeds the entity graph with
stubs for the services, teams, data types, and tools mentioned, and generates a Day-1 brief from
those answers without any uploaded documents.
COMPLEXITY: Low
VALUE: High — this is the front door. Without it, Tank cannot serve the first hire at all.
```

---

```
GAP: Chat degrades with an empty knowledge base
JOURNEY PHASE: Discovery
CURRENT STATE: The chat system retrieves KB chunks and entity cards for context before every
response. With an empty KB, retrieval produces nothing, and responses default to generic Claude
outputs without Tank's specific framing, tools, or structure. The 15 chat tools — search_kb,
get_entity, find_control_gaps, etc. — return empty results or errors.
WHAT'S MISSING: A "discovery mode" for chat that works when the KB is sparse or empty. Instead
of silently retrieving nothing, Tank should acknowledge what it doesn't know, ask the user to
fill in gaps, and maintain a running "what I've learned so far" model built from conversation
alone.
PROPOSED FEATURE: Empty-KB Chat Mode. When the KB is sparse (fewer than N chunks), Tank shifts
to an active-discovery posture: it asks clarifying questions in response to user queries, treats
user answers as ephemeral KB contributions, and surfaces suggestions like "this would be a good
thing to ingest once you have the architecture doc." Answers given in chat can optionally be
confirmed and persisted as entity stubs.
COMPLEXITY: Low
VALUE: High — required for Day 1 usefulness.
```

---

```
GAP: No leadership communication layer
JOURNEY PHASE: Assessment, Program
CURRENT STATE: Tank produces detailed technical artifacts — threat models, risk registers, IAM
audit reports, compliance evidence maps. None of these are directly usable by a non-security
audience. The existing reports are written for the security engineer, not for their CTO, CFO, or
board.
WHAT'S MISSING: Report types that translate technical findings into business language. The first
hire will be asked "so how secure are we?" within their first two weeks and regularly thereafter.
The answer needs to be in language that makes business sense: what data is at risk, what a
breach would cost, what the company is liable for, what investment is required to fix it.
PROPOSED FEATURE: Leadership Communication Templates. Three new report kinds: (1) State of
Security — monthly one-page summary of program health, top risks, and actions taken, written
for a non-technical reader; (2) Initial Assessment — the 30-day "here's what I found" brief with
business-impact framing for every high/critical finding; (3) Program Roadmap — 12-month plan
with milestone descriptions, investment requirements, and risk reduction narrative. All three
should be generated from the existing KB and risk register, not require new data entry.
COMPLEXITY: Low
VALUE: High — this is the output the first hire is evaluated on by leadership.
```

---

```
GAP: No prioritization engine
JOURNEY PHASE: Assessment, Foundation
CURRENT STATE: The risk register scores findings by inherent and residual likelihood × impact
(1–5). This produces a list sorted by score. With 40 items, the top 10 may all be tied at "4×4"
with no way to differentiate them. There is no way to ask "given zero budget and my specific
company context, what do I fix first?"
WHAT'S MISSING: A recommendation system that goes beyond L×I scoring to incorporate: what data
is exposed if this finding is exploited, what the regulatory consequence is, what compensating
controls exist, how hard it is to exploit, and how likely this company specifically is to be
targeted. The output should be a concrete "do these 5 things this quarter" recommendation, not a
sorted list.
PROPOSED FEATURE: Prioritization Engine. Tank analyzes the risk register in the context of the
company's KB — known data stores, compliance requirements, service criticality, existing controls
— and produces a quarterly action plan: the top 5 items to address, a rationale for each, and
what "done" looks like. The recommendation must be opinionated; it cannot hedge into "it
depends."
COMPLEXITY: Medium
VALUE: High — the first hire's most pressing daily question, and currently unanswered.
```

---

```
GAP: No compliance framework selection wizard
JOURNEY PHASE: Assessment
CURRENT STATE: Tank can ingest compliance framework documents (NIST CSF, etc.) and map evidence
to controls. It assumes the user already knows which framework applies. There is no guidance for
a first hire who knows their company needs "something" but doesn't know what.
WHAT'S MISSING: A guided decision process for selecting the right compliance framework. This is
often partly a business decision (what do enterprise customers require? what do investors expect?
what is the industry norm?) and partly a technical one (what does achieving it actually require,
and is the company anywhere close?).
PROPOSED FEATURE: Compliance Selection Wizard. A structured questionnaire covering: industry,
customer type, data handled, geographic reach, investor requirements, and known contractual
obligations. Output: a ranked recommendation (e.g., "SOC 2 Type I is right for you, here's why,
here's what achieving it requires, here's an honest timeline") plus a gap analysis against the
current KB. The wizard should be honest about what the chosen framework will cost in time and
engineering effort — not just what it is.
COMPLEXITY: Low
VALUE: High — this question comes up in the first 30 days at nearly every early-stage company.
```

---

```
GAP: No security policy scaffolding
JOURNEY PHASE: Foundation
CURRENT STATE: Tank can analyze existing policies that are ingested as documents. It does not
generate them. The first hire who needs to write their company's first Acceptable Use Policy,
Incident Response Policy, or Secure Development Lifecycle must start from scratch or use generic
templates downloaded from the internet.
WHAT'S MISSING: First-draft policy generation anchored to the specific company. A generic AUP
is nearly useless; an AUP that mentions the company's actual systems, data types, and tooling is
immediately ownable and editable.
PROPOSED FEATURE: Security Policy Scaffolding. Tank generates first drafts of the five most
critical foundational policies — Acceptable Use, Incident Response, Secure Development
Lifecycle, Vulnerability Management, Data Classification — using the discovered KB as context.
The drafts use the company's actual service names, cloud providers, and data categories. They are
starting points, not finished documents; the first hire owns and edits them. Generated policies
are stored as living artifacts in Tank, not just exported files.
COMPLEXITY: Medium
VALUE: High — saves the first hire 5–10 hours per policy and results in policies that are
immediately relevant to the company's actual environment.
```

---

```
GAP: No guided org discovery workflow
JOURNEY PHASE: Discovery
CURRENT STATE: Tank ingests documents that the user uploads or points it to. It does not help
the user *find* what to ingest. The first hire must independently discover that the GitHub org
has 40 repos, that there's a Confluence space with architecture docs, that the SRE team maintains
a CMDB spreadsheet — and then manually feed each of these to Tank.
WHAT'S MISSING: A workflow that guides the first hire through systematically discovering what
exists. Most companies leave a trail: GitHub org membership, Confluence spaces, Jira projects,
deployment configs, cloud resource tags.
PROPOSED FEATURE: Org Discovery Wizard. A guided sequence that helps the first hire inventory
what exists: (1) GitHub org scan — connect org token, enumerate repos, suggest which to ingest
based on repo names and descriptions; (2) Team directory import — CSV or SCIM-style import of
people, teams, and roles; (3) Manual service entry — a structured form for entering services
discovered in conversation ("I just learned from the SRE team that we run a payments service on
EC2 with RDS backend"). Each step produces entity stubs that enrich the graph.
COMPLEXITY: Medium
VALUE: High — reduces the first hire's discovery friction from days to hours.
```

---

```
GAP: No security stack inventory template
JOURNEY PHASE: Discovery
CURRENT STATE: The first hire needs to know what security tooling currently exists — or doesn't
exist. Tank has no structured place to capture this inventory, and no workflow to help the first
hire gather it systematically.
WHAT'S MISSING: A structured checklist-driven flow that catalogs the security tooling landscape:
identity provider, MFA status, secret management, SIEM, WAF, EDR, vulnerability scanner, DLP,
network segmentation, backup and recovery. For each category: does it exist? What tool? How
mature is it? This inventory is the first thing a CISO or auditor asks for.
PROPOSED FEATURE: Security Stack Audit. A structured inventory template covering 12–15 security
capability categories. For each: current tool (or "none"), deployment status, coverage (what's
in scope), and known gaps. Saved as a living document in Tank, surfaced in the program dashboard,
and used by the prioritization engine as input ("no EDR means endpoint threats have no detection
coverage").
COMPLEXITY: Low
VALUE: Medium — foundational input for multiple other features.
```

---

```
GAP: No guided task list for the first 90 days
JOURNEY PHASE: All
CURRENT STATE: Tank's tenure-aware lens shifts framing from Map to Prioritize to Execute to
Maintain, but it does not produce a concrete task list for what the first hire should be doing in
any given week. The nudge system surfaces reminders and follow-ups but assumes the user already
knows their priorities.
WHAT'S MISSING: A milestone-driven 90-day checklist that tells the first hire specifically what
to do in each week, adapted to their company's context. Not a generic "week 1: meet your team"
template — an actual Task list informed by what Tank has discovered about their specific situation.
PROPOSED FEATURE: 90-Day Plan Generator. Produced during onboarding (or regeneratable on
demand), this is a concrete task list organized by week, adapted to the first hire's role, KB
state, and risk landscape. Items check off as they're completed. Tank surfaces relevant tasks in
the morning digest ("this week: generate threat model for payments service, draft IR runbook for
data breach scenario, schedule tabletop with SRE team"). Progress is visible on the home
dashboard.
COMPLEXITY: Low
VALUE: Medium — the first hire often doesn't know what they should be doing; this makes the
right next action obvious at every stage.
```

---

```
GAP: No vulnerability management workflow
JOURNEY PHASE: Foundation
CURRENT STATE: The CVE feed watcher monitors for new CVEs and creates vulnerability entities.
The vulnerabilities table exists. There is no UI for triaging, assigning, tracking, and closing
vulnerabilities. The first hire cannot run a vulnerability management process inside Tank.
WHAT'S MISSING: A triage workflow: new CVE arrives → affected services identified → severity
assessed → owner assigned → remediation tracked → closed. This is distinct from the risk
register (which handles strategic risks) — this is operational vulnerability tracking.
PROPOSED FEATURE: Vulnerability Management Workflow. A triage queue (new CVEs and scanner
findings land here), per-CVE detail view with KB-driven affected-service mapping, assignment to
service owner, due-date tracking, and a weekly "vulnerability aging" nudge. Integrates with the
risk register (high-severity CVEs can be promoted to risk entries) and the program dashboard
(open vuln count, mean-time-to-close).
COMPLEXITY: Medium
VALUE: Medium — required for the Foundation phase but not needed on Day 1.
```

---

```
GAP: No security champions enablement tools
JOURNEY PHASE: Program
CURRENT STATE: Tank has no features specifically for building or managing a security champions
program — the distributed model where embedded engineers in each team carry security
responsibilities.
WHAT'S MISSING: The first hire at a 200-person company cannot be in every design review and
code review. They need multipliers. Building a security champions program is a standard solution,
but most first hires don't know where to start.
PROPOSED FEATURE: Security Champions Toolkit. A lightweight set of resources Tank can generate
and track: (1) Security champions program proposal document (for leadership approval); (2) Role
definition and expectation-setting doc (for nominees); (3) Monthly champion briefing (agenda
template, current top risks for each team, training links); (4) Champions registry in the team
entity cards (mark which engineer is the security champion for each team).
COMPLEXITY: Medium
VALUE: Medium — important at Day 90+, not blocking early phases.
```

---

```
GAP: No engineering culture and buy-in tools
JOURNEY PHASE: Program
CURRENT STATE: Tank has no features that help the first hire build relationships with the
engineering org or measure the security culture. Security culture assessment — do engineers care?
do they know what to do? — is not tracked or surfaced anywhere.
WHAT'S MISSING: Tools to help the first hire understand and improve the engineering team's
security posture and engagement. This is as much a people problem as a technical one.
PROPOSED FEATURE: Engineering Engagement Tracker. A lightweight set of signals: (1) Security
training coverage (who has completed what); (2) Design review participation (which teams are
submitting reviews vs. skipping); (3) Vulnerability fix rate by team (who closes their assigned
CVEs on time?); (4) Incident response participation (who shows up to tabletops?). Aggregated into
a "team security engagement" view that helps the first hire identify where to invest relationship
effort. This is not a punitive scorecard — it's the first hire's map of where to focus enablement.
COMPLEXITY: High
VALUE: Medium — powerful but requires the other gaps to be filled first.
```

---

## Section 5: What Tank Becomes

A first security engineer at a 200-person SaaS startup opens Tank on their first day. They have nothing: no architecture docs, no asset inventory, no threat models, no security policies, no incident history. The engineering org has been shipping features for three years without a security function. Their manager — the CTO — expects them to "get us SOC 2 ready within 12 months" and has a vague sense that there are probably some things to fix.

Tank doesn't ask them to upload a document. It asks them a question: "Tell me about your company. What does it build?"

Over the next 15 minutes, Tank asks 20 structured questions: What type of customers do you serve? What data do they trust you with? What cloud providers does your infrastructure run on? Do you have a secrets manager? Is MFA enforced on your identity provider? Have you ever had a security incident? Who owns your most critical services? The engineer answers from memory, imprecisely, and Tank is fine with that — it marks guesses as guesses and gaps as gaps.

At the end, Tank has a skeleton knowledge graph: seven service stubs, three team entities, two known data types (customer PII and payment data), one confirmed tool (AWS), and a list of fifteen things it doesn't know yet. It generates a Day-1 Brief: "Based on what you've told me, your highest-priority areas are authentication (no MFA confirmed), payment data handling (PCI DSS likely applies), and incident response (none exists). Here's who you should meet in week one and what to ask them. Here's a preliminary reading list."

Over the next two weeks, the engineer conducts interviews with engineers and pulls whatever docs they can find — a Terraform repo, a Confluence architecture page, an old runbook in a Google Doc. Each gets fed into Tank. Each enriches the graph. Tank starts surfacing insights: "This Terraform config shows your RDS instance has `deletion_protection = false` and no automated backup policy. I've added this to your risk register as a medium-severity finding." The entity graph fills in. By Day 14, Tank knows about twelve services, their dependencies, the teams that own them, and a growing list of unknowns.

At Day 30, the engineer has a risk register with 28 items. They open Tank and ask: "Given everything we know, what should I fix first?" Tank comes back with a prioritized top 5 — not sorted by CVSS, but by a synthesis of data exposure, regulatory consequence, and exploitability. Item 1: "Payment service has no WAF and is directly internet-exposed, handling Stripe webhook callbacks that are not signature-verified. Customer financial data is at risk. Remediation: 2 engineer-days." That's a recommendation the engineer can act on today.

The same day, Tank generates the first leadership report. The engineer sends it to the CTO: a two-page State of Security brief that says, in plain language: "In month one I found 28 risks across your 12 critical services. Five are urgent. Here's what they mean for the business. Here's what I'm doing about them. Here's what I need to fix the rest."

At Day 60, the engineer has produced Tank-scaffolded first drafts of five security policies. The policies name the company's actual services, actual cloud provider, actual authentication system. The IR policy says "for a credentials compromise of the Vault service, follow this runbook" — and there is a runbook, generated by Tank and confirmed by the engineer. The decisions log has 15 entries: the choice of NIST CSF as the compliance framework, the accepted risk on the legacy service that's too costly to fix right now, the deferred decision on WAF vendor. These decisions are dated, rationed, and can be shown to auditors.

At Day 90, the engineer walks into their first board meeting. Tank produced the Program Roadmap: a 12-month plan that shows where security was on Day 1, where it is now, and what it will look like in a year. The risk register has closed 12 of the 28 items and added 15 new ones. The program dashboard shows green on IR readiness, yellow on vulnerability management, red on compliance — honest, not performative. The board asks three questions. The engineer has answers for all of them.

The engineer doesn't feel like they're drowning anymore. They have a system.

This is what Tank becomes.

---

## Section 6: Proposed Redesign Principles

These eight principles should guide every design and implementation decision during the redesign. When two choices are in tension, resolve it using these principles, in order.

**1. Tank must work before the first document is ingested.**
The front door cannot be an upload form. The first hire's first session should produce something useful even if they bring nothing. Every feature that is currently gated on KB content needs a graceful zero-KB mode.

**2. Discovery is a first-class workflow, not a precondition.**
The current model treats "document ingestion" as setup that happens before the real work begins. For the first hire, discovery *is* the real work — for the first two weeks. Tank should actively assist with it: structured questions, org scanning, meeting prep, notes-to-KB — all in support of building the initial knowledge graph from conversation and investigation, not just from uploaded files.

**3. Every output Tank produces must be shareable with non-security stakeholders without editing.**
The first hire does not have time to translate Tank's outputs for leadership. Tank's reports, risk summaries, program dashboards, and policy scaffolds must be written in language that a CTO, CFO, or board member can understand and act on. Technical precision is secondary to business clarity.

**4. Tank should always surface the most important next action at every stage.**
A tool that requires the user to know what to do next is a tool for experts. The first hire is not an expert in this company yet. At every tenure phase, Tank should have an opinion about what matters most right now and surface it proactively — in the morning digest, on the home dashboard, in the 90-day plan tracker, and in response to direct chat questions.

**5. "I don't know yet" is valid data.**
Gaps in knowledge are as important as confirmed facts. Tank should track what it doesn't know — services it hasn't been told about, data types that are unclassified, threats that are theorized but unconfirmed — and treat those gaps as first-class items that need resolution, not just as absence of information.

**6. The first 90 days is a structured journey, not an open-ended tool.**
Tank should feel like a guide during the first 90 days, not a blank canvas. The tenure-aware lens already provides the phases; the redesign should make those phases concrete: specific milestones, specific outputs, specific "this is what done looks like." After Day 90, the first hire graduates to the daily-companion mode that Tank has always been good at.

**7. Tank generates starting points; it doesn't only analyze existing artifacts.**
The current Tank is an analyzer. The redesigned Tank is also a generator. Policies, runbooks, roadmaps, risk recommendations, org inventory, 90-day plans — these should all be generated by Tank from available context, not assembled manually by the user. The first hire edits what Tank generates; they don't start from scratch.

**8. Building engineer trust and leadership buy-in is as important as finding risk.**
Security programs fail not because the engineer didn't find enough risks, but because they couldn't get the engineering org or leadership to care. Tank should actively support the social and communicative work of the first hire, not just the technical work. Meeting prep, leadership reports, security champions program materials, and design review onboarding guides are all first-class outputs.

---

## Section 7: Recommended Build Order

The ordering below is driven by a single question: what is the minimum set of changes that makes Tank genuinely more useful than it is today for the first hire on Day 1? Everything in Phase 1 satisfies that. Everything after builds on it.

---

### Phase 1 — First hire can use Tank on Day 1
*Build this first. Without it, nothing else matters.*

**Quick-Start Intake Interview (NEW)**
The first thing a new user encounters. Twenty structured questions about company, stack, data, team, and existing controls. Produces: entity stubs for the knowledge graph, an initial risk hypothesis, and a Day-1 brief — all before a single document is uploaded. This is the front door. It must exist before any other redesign is visible.

**Onboarding Flow Revision (EVOLVE)**
The current onboarding configures a companion. The new onboarding conducts a discovery interview. Role selection, internal TLD, and digest configuration move to Settings; the onboarding becomes the intake interview above. A returning user who skipped onboarding should be offered the intake interview from the home dashboard.

**Chat Empty-KB Mode (FIX)**
When the KB is sparse, chat should shift to a discovery posture rather than returning empty results. Tank should acknowledge what it doesn't know, ask clarifying questions, and treat conversation answers as provisional KB entries. This is a behavioral change to the chat loop, not a new feature, and it can be done in parallel with the intake interview.

**Outcome:** A first hire can open Tank, spend 15 minutes in the intake interview, and have a Day-1 brief plus a skeleton KB — with no documents required. This alone transforms Tank from "needs docs to be useful" to "useful on Day 1."

---

### Phase 2 — Discovery phase tools (Days 1–14)
*Once the front door exists, build what the first hire needs in the first two weeks.*

**Org Discovery Wizard (NEW)**
GitHub org scan, team directory import (CSV), and manual service entry form. Produces entity stubs for every repo, team, and service discovered. Integrates with the existing watchers (GitHub repo watcher already exists; this extends it to org-level discovery).

**Security Stack Audit Template (NEW)**
A structured inventory form covering 12–15 capability categories. Saved as a living document in Tank, surfaced in the program dashboard. Used by the prioritization engine as context for "what compensating controls exist."

**Leadership Communication Templates (NEW)**
State of Security (monthly brief), Initial Assessment (30-day findings summary), and Program Roadmap (12-month plan). Generated from the existing KB and risk register. These are new report kinds in the `REPORT_REGISTRY`, following the existing pattern in `reports.py`.

**90-Day Plan Generator (NEW)**
A milestone-driven task list produced during onboarding and surfaced in the daily digest. Items adapt to KB state — as threat models are completed and policies are drafted, the plan updates. Visible on the home dashboard under the current nudge/followup panels.

**Outcome:** By the end of week two, the first hire has a structured asset inventory, a populated KB, leadership-ready first reports, and a clear task list for the next 75 days.

---

### Phase 3 — Assessment phase tools (Days 15–45)
*The first hire now has enough context to evaluate. Give them tools to do it.*

**Compliance Framework Selection Wizard (NEW)**
Decision-tree questionnaire → ranked compliance framework recommendation with gap analysis. A new onboarding sub-flow triggered when the user first navigates to the compliance section. Output stored as a decision in the decisions log (kind: design_choice).

**Prioritization Engine (NEW)**
Analyzes the risk register in KB context → produces a quarterly top-5 action plan with rationale and "done looks like." Surfaced as a new section on the Security Program Dashboard and as a monthly nudge. This is the most complex new feature in Phase 3 but also the most valuable.

**Initial Assessment Report (EVOLVE)**
A new report kind — distinct from the existing threat_landscape and cross_service_gaps reports — that synthesizes the first 30 days of discovery into a leadership-ready assessment. Business-language finding descriptions, compliance gap summary, and recommended immediate actions.

**Outcome:** By Day 45, the first hire has a compliance path, a prioritized action list, and a leadership brief that explains what they found and what it means for the business.

---

### Phase 4 — Foundation phase tools (Days 30–60)
*The first hire is building. Give them generators, not blank pages.*

**Security Policy Scaffolding (NEW)**
Five first-draft policies generated from the KB. Stored as living artifacts in Tank (follow the existing workstream artifact pattern: `policies_store.py`, router, list + detail templates). Editable in-app. Linked to the decisions log (each policy contains implicit design choices that should be tracked explicitly).

**Vulnerability Management Workflow (EVOLVE)**
Triage queue for CVE feed findings, per-vulnerability detail with KB-driven service mapping, assignment, due-date tracking. Extends the existing `vulnerabilities` table (already present) with a triage UI. Integrates with the program dashboard (open vuln count, mean-time-to-close).

**Guided Task List (integrated with 90-Day Plan from Phase 2)**
By Phase 4 the 90-Day Plan is already live; Foundation-phase tasks are populated in it automatically as the KB grows. No new feature required — this is content and logic added to the planner built in Phase 2.

**Outcome:** By Day 60, the first hire has drafted their first policies, has an operational vulnerability management process, and has a program dashboard showing measurable progress from Day 1.

---

### Minimum Viable Redesign

If only Phase 1 ships, Tank is already meaningfully more useful than it is today for the first hire. The quick-start intake interview, the onboarding revision, and the chat empty-KB mode together remove the single biggest barrier: the requirement to have documents before Tank does anything. Everything in Phases 2–4 adds depth and specificity to the experience, but Phase 1 alone is shippable and valuable.

Do not ship Phase 2 without Phase 1. The org discovery wizard and leadership templates are only useful if there's already a bootstrapped KB to query. Phase 1 is the prerequisite for everything else.

---

*This document was produced from a full codebase read of Tank at commit b92ab25. Feature inventory covers all 25 major feature areas. Gap analysis reflects the capabilities of Tank as of 2026-05-28. Section 5 vision narrative describes the target end state, not current functionality.*
