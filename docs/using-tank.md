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

Tank has 13 tools:

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
