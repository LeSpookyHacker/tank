# Continuous learning + memory (Phase 15)

The polish layer that turns Tank from a "good in your first 90 days"
tool into one that's still earning its keep at 18 months. Four
features: lessons-learned DB, glossary builder, personal ownership
dashboard, and the security philosophy doc.

---

## Lessons-learned DB (`/lessons`)

A searchable, tag-indexed corpus of "things we learned the hard way."

### How lessons get created

Auto-populated from three sources:

- **Postmortems on publish** —
  `lesson_extractor.extract_from_postmortem()` pulls 1-4 generalizable
  lessons (not "Q2 2026 Vault sidecar outage", but "when webhook
  signing was disabled, replay attacks became possible").
- **Design reviews on rejection** —
  `lesson_extractor.extract_from_design_review()` pulls 1-3 lessons
  from the rejection rationale, tagged with the review's risk
  areas.
- **Tabletops on capture** — each bullet you record after running a
  tabletop becomes a lesson tagged with whatever tags you supplied.

Also manual: `POST /api/lessons` to drop one directly.

### Schema

```sql
lessons (
    id, title,
    body_md, body_md_redacted,
    source_kind,         -- postmortem|design_review|tabletop|incident|user
    source_id,
    tags,                -- JSON array of strings
    scope_entity_ids,    -- JSON array
    captured_at
)
```

### Retrieval

| Surface | Tool |
| --- | --- |
| Browser | `/lessons?q=...&tag=...` — search + filter |
| API | `GET /api/lessons`, `/search?q=...`, `/tag/{tag}` |
| Chat | `search_lessons(query, tag?)` — Sonnet calls this when the user asks "has this happened before" |

> ⬜ **Screenshot placeholder**: lessons page filtered by tag.
>
> ![Lessons learned](../images/feature-lessons.png)

---

## Personal ownership dashboard (`/me`)

Where you mark what's yours and see its current risk.

### Claiming ownership

On a Service entity's detail page, click **"I own this"**. Stored in
`owned_entities` with `role='owner'` (other roles: `reviewer`,
`consulted`, `informed` — set via `POST /api/me/owned` with the role
field).

### Risk score

For each owned entity, Tank computes a coarse 0-10 risk score
weighted across:

- **TM drift** — no TM → +3; TM exists but arch hash differs → +2.
- **Unaddressed threats** — high-likelihood / high-impact threats in
  the latest TM with no `suggested_controls` → +1.5 (capped at 1).
- **Expired decisions** — decisions scoped to this entity whose
  `expires_at` has passed → +0.7 each.
- **Open postmortem follow-ups** — followups with this entity as
  `related_entity_id` and `status='open'` → +0.5 each.

Capped at 10.0. Not a CVSS replacement — a coarse indicator.

> ⬜ **Screenshot placeholder**: ownership dashboard with risk bars.
>
> ![Ownership dashboard](../images/feature-ownership.png)

### Schema

```sql
owned_entities (
    user_id,         -- DEFAULT 1; reserved for future multi-user
    entity_id,
    role,            -- owner|reviewer|consulted|informed
    set_at,
    PRIMARY KEY (user_id, entity_id)
)
```

---

## Glossary builder (`/glossary`)

Captures company-specific jargon so Tank's chat replies use your
vocabulary. **Not PII** — these are project names, internal service
nicknames, acronyms. The glossary is intentionally NOT redacted; it
exists to enrich Tank's display layer, not hide things.

### How candidates surface

- **Manual discover** — `POST /api/glossary/discover` runs Sonnet
  over a sample of recent KB chunks via
  `prompts/glossary_extract.md`. Sonnet returns
  `[{term, definition, aliases}]` filtered to company-specific
  phrases — skipping standard English, standard infosec vocabulary,
  standard cloud terms.
- **Future hook**: post-ingest auto-trigger (deferred; manual for
  now).

### Confirm / reject

Pending candidates show in the page's "Pending" section. One-click
confirm promotes them into the confirmed glossary; reject hard-deletes
them. Confirmed terms get included in the chat's cached KB block
when relevant.

> ⬜ **Screenshot placeholder**: glossary page with 3 pending + 12 confirmed.
>
> ![Glossary](../images/feature-glossary.png)

### Schema

```sql
glossary (
    id, term, term_normalized,
    definition,
    aliases,             -- JSON array
    confirmed,           -- 0|1
    first_seen_doc_id,
    occurrences,
    updated_at
)
```

---

## Security philosophy doc (`/philosophy`)

One curated long-running document Tank co-authors with you over time.
It captures the *stances* you've taken on how security should work
at this company.

### Lifecycle

- **Day-30 anniversary**: auto-seeds via
  `philosophy.seed()`, drawing from your first month of decisions
  log + tabletops + (eventually) freewrite prompts. Prompt:
  `philosophy_seed.md`.
- **Day-60 / 90 / 180 / 365 anniversaries**: auto-evolves via
  `philosophy.evolve()`. Sonnet keeps stances that still hold,
  refines wording, removes contradicted ones, adds 1-3 new
  reflecting recent decisions. Prompt: `philosophy_evolve.md`.

Manual trigger: `POST /api/philosophy/seed` or `/evolve` at any time.

### What it contains

A `PhilosophyDoc`:

- **intro** — 3-4 sentences on your overall approach.
- **stances** — 3-6 items, each:
  - `title` (4-8 words, concrete: "Defense in depth over single
    chokepoints")
  - `body_md` (2-4 sentences)
  - `related_decision_ids` (linked back to the decisions log)
- **open_questions** — 1-3 things you haven't decided yet but know
  you need to.

Persisted as a `reports` row with `kind='philosophy'`. The pointer
lives in `app_state.philosophy_doc_id`.

> ⬜ **Screenshot placeholder**: philosophy doc rendered.
>
> ![Security philosophy](../images/feature-philosophy.png)

---

## Security-focused anniversary retros

Alongside the existing generic anniversary retro (Phase 8), Day-30 /
60 / 90 / 180 / 365 also fires an `anniversary_security_<N>` report
via `anniversary_security.generate()`. Same `AnniversaryRetro` shape
but keyed to security work in the window:

- **what_you_built** — TMs authored, controls confirmed, detections
  added, runbooks written.
- **what_you_learned** — lessons that emerged from postmortems /
  tabletops / journal.
- **what_drifted** — TMs that fell behind arch, expired decisions
  not reaffirmed, postmortem action items still open.
- **next_30_days** — 3-5 prioritized action items.

Stored as a separate `reports` row so you can compare to the generic
retro side-by-side.

---

## Phase 15 nudges

- **`lesson_to_recall`** — fires when a new design review touches a
  tagged area; surfaces a relevant past lesson. (Wired in code;
  appears in nudges_store when the trigger fires.)
- **`glossary_unconfirmed`** — N candidate terms awaiting confirm.
- **`ownership_drift`** — an entity you "own" has new threats not in
  its TM.
- **`philosophy_update_due`** — quarterly; "your philosophy doc
  hasn't been touched in 90 days; here's what changed."

---

## Cost guidance

- Lesson extraction on a postmortem publish: ~$0.01 (added to publish
  latency by ~5-10s).
- Lesson extraction on a design-review rejection: ~$0.005.
- Glossary discover run: ~$0.01-$0.03 per invocation.
- Philosophy seed (Day-30): ~$0.05.
- Philosophy evolve (Day-60/90/180/365): ~$0.03.
- Anniversary-security report: ~$0.05 (fires alongside the generic
  retro for free given prompt cache).
