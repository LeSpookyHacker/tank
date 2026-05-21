# First run — the onboarding flow

Tank's onboarding is **conversational, not a form**. It takes about
7 minutes and produces a printable **Day-1 brief** at the end. You
go through it once.

---

## Before you start

Have these handy:

- Your offer letter or job description (or a freewrite of the role).
- Your calendar for the first 2 weeks (any `.ics` export, or just
  copy-paste).
- A handful of docs your employer gave you (architecture overview,
  onboarding wiki, anything). Tank ingests them in the background
  while you finish the intake.

---

## The five steps

> ⬜ **Screenshot placeholder**: onboarding step-1 (role frame).
>
> ![Onboarding role pick](images/onboarding-1-role.png)

### Step 1 — Role frame

Pick: **Staff IC**, **Manager**, or **Both**. This sets the lens
for chat replies, reports, and the home dashboard:

- **Staff IC**: technical depth, code-level reasoning, security-design
  framing.
- **Manager**: org context, stakeholder map, executive-summary framing.
- **Both** (default): hybrid — useful for Staff/Manager hybrids and
  anyone unsure.

You can switch later in Settings. Switching mid-conversation **forks**
the conversation rather than mutating; both versions stay in your
list.

### Step 2 — Scope sketch

Paste your offer letter / JD / freewrite. Tank extracts:

- **Domain** — what part of the business you're responsible for.
- **Org** — your team, your manager.
- **Manager** — name (becomes a Person entity).
- **Priorities** — up to 5 chips you can edit before saving.

You don't have to fix anything. Whatever's wrong, you can correct in
Settings or just by chatting ("actually, my manager is Priya, not
Tom").

> ⬜ **Screenshot placeholder**: onboarding step-2 (scope chips).
>
> ![Onboarding scope](images/onboarding-2-scope.png)

### Step 3 — Calendar dump

Paste a chunk of your calendar or upload an `.ics` file. Tank parses
each event for:

- **Who** (attendees) → seeds the Person graph.
- **When** → drives the auto pre-meeting brief scheduler.
- **Recurrence** → identifies your 1:1 cadence.

If you'd rather skip this step, click "skip" — you can wire up the
ICS watcher later in Settings → Integrations.

### Step 4 — Drop initial docs

A simple drop zone for your starter pack. Tank ingests in the
background while you finish Step 5. No required schema:

- Markdown, PDF, DOCX → architecture / process docs
- PNG / JPG → diagrams (Sonnet vision extracts entities + edges)
- CSV / JSON → CMDB rows
- Git repos → pass a local path; Tank summarizes (manifests, CI,
  Dockerfiles, auth grep hits, README) **without sending raw code**

You'll see the ingest panel populate in real time.

> ⬜ **Screenshot placeholder**: onboarding step-4 ingest progress.
>
> ![Onboarding ingest](images/onboarding-4-ingest.png)

### Step 5 — Cadence

Set:

- **Daily digest time** — when the morning digest fires (default 08:00).
- **Reflection day** — when the Friday-afternoon weekly reflection
  fires (default Friday 16:00).

That's it. Tank stamps `app_state.tenure_started_at = now()` and
takes you to your Day-1 brief.

---

## The Day-1 brief

Generated at the end of onboarding by Sonnet 4.6 over the
freshly-built KB. It contains:

1. **Scope echo** — Tank reads back what it understood your role to
   be (2-3 sentences).
2. **Top 5 entities** — the services/people/data stores most relevant
   to your stated scope, one line each.
3. **3 questions to ask in week 1** — concrete, with named people to
   ask them of.
4. **3 docs to read first** — ranked, citing chunks from what you
   just ingested.
5. **3 meetings to set up** — with whom and why.

Render as Markdown in the browser, downloadable as PDF (Markdown
export always works; PDF needs `weasyprint` — install if you want
it).

> ⬜ **Screenshot placeholder**: Day-1 brief rendered.
>
> ![Day-1 brief](images/onboarding-5-day1-brief.png)

You also get pre-filled **follow-ups** — Tank offers to seed the
"3 meetings to set up" as actionable items in your follow-ups inbox
with one click.

---

## After onboarding

The home dashboard takes over. Three immediate things to do:

1. **Click into a Service entity** from `/entities` and click
   "Generate threat model (v2)". This kicks off your first
   versioned threat model.
2. **Mark a few services as yours** via the "I own this" button.
   Tank's `/me` ownership dashboard wakes up.
3. **Open the chat** and ask: *"Who owns payments-api?"* — that's the
   golden-path smoke test.

The next morning, you'll see your first digest. After two weeks
Tank's lens auto-shifts from "map" to "prioritize." At Day-30, the
philosophy doc gets seeded.

---

## Re-running onboarding

You can't accidentally re-run it: `app_state.onboarded = 1` is
sticky. If you need to truly re-onboard:

1. Settings → "Wipe everything" (you'll have to type `delete tank`).
2. Or `rm ~/.tank/db.sqlite` and restart Tank.

The wipe also clears your KB, decisions, threat models, lessons, and
philosophy doc. Run a backup first (`~/.tank/backups/` has weekly
snapshots if you've been on it a while).
