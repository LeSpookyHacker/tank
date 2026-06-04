# Security workstreams (Phase 13)

The artifacts a Sr/Staff/Mgr security engineer writes weekly:
**design reviews**, **postmortems**, **tabletop exercises**, **on-call
handoff briefs**, and a **weekly security digest**. Tank hosts the
workflow for each.

---

## Design reviews (`/design-reviews`)

A hosted intake → checklist → approval flow that ends up spawning
decisions automatically.

### Flow

1. **Freewrite** — title + a paragraph or two describing the design.
2. **Sonnet seeds the intake** via `prompts/design_review_intake.md`:
   - 2-3-sentence scope summary
   - 3-6 likely risk areas (specific to your design, not generic)
   - 3-6 missing-info questions the reviewer should demand
   - Up to 5 suggested reviewers from your KB
   - 6-10-item checklist keyed to the design across categories:
     authn / authz / crypto / data / deps / blast / logging / tm /
     rollout
3. **Work the checklist** — each item has a `checked` flag + free-form
   `notes`. Save as you go.
4. **Status transitions** — `intake` → `reviewing` → `approved` |
   `rejected` | `withdrawn`.
5. **On approve** — spawn one or more decisions from the review.
   Each gets `source='design_review'` and links back via the
   review's `decisions_json`. The review's `scope_entity_ids` are
   inherited automatically.
6. **On reject** — Phase 15 hook auto-extracts lessons via
   `lesson_extractor.extract_from_design_review()`. The rejection
   rationale becomes a queryable lesson tagged with the design's
   risk areas.

The checklist itself is part of the intake prompt's structured
output — there's no separate `design_review_checklist.md`. Default
checklist categories (authn, authz, crypto, data, deps, blast,
logging, tm, rollout) are seeded by Sonnet against your specific
design via `prompts/design_review_intake.md`.

> ⬜ **Screenshot placeholder**: a design review mid-checklist.
>
> ![Design review checklist](../images/feature-design-review.png)

### Schema

```sql
design_reviews (
    id, title, status,
    requester,
    scope_entity_ids,    -- JSON array
    body_md, body_md_redacted,
    checklist_json,      -- [{item, checked, notes, category}]
    decisions_json,      -- spawned decision IDs
    created_at, updated_at
)
```

### API

| Endpoint | What |
| --- | --- |
| `POST /api/design-reviews` | Create from freewrite (runs intake prompt) |
| `GET /api/design-reviews` | List, optionally filtered by status |
| `GET /api/design-reviews/{id}` | Detail |
| `PUT /api/design-reviews/{id}/checklist` | Persist checked + notes |
| `PUT /api/design-reviews/{id}/status` | Move through statuses |
| `POST /api/design-reviews/{id}/decisions` | Spawn a decision |

---

## Postmortems (`/postmortems`)

Author postmortems in Tank instead of importing them post-hoc.
Sonnet drafts the structured fields from your freewrite.

### Flow

1. **Freewrite** — title + everything you remember + (optional)
   severity guess.
2. **Sonnet drafts** via `prompts/postmortem_draft.md`:
   - Summary (plain-English for non-engineers)
   - Timeline (bullets, with T+0 / T+15m markers if no timestamps)
   - What failed (proximate cause)
   - Why (mechanism)
   - Contributing factors
   - Mitigations applied during the incident
   - Action items (each future-tense, owner-able)
   - Services affected
   - Severity guess
3. **Edit** in the structured editor.
4. **Publish** triggers two things automatically:
   - Each action item → a row in `followups` with
     `source_kind='postmortem'`.
   - Phase 15 hook: `lesson_extractor.extract_from_postmortem()`
     pulls 1-4 generalizable lessons into `/lessons`.

> ⬜ **Screenshot placeholder**: postmortem editor with fields filled.
>
> ![Postmortem editor](../images/feature-postmortem-editor.png)

### Schema

```sql
postmortems_drafts (
    id, title,
    incident_date, severity,    -- sev1|sev2|sev3
    status,                     -- draft|published|withdrawn
    fields_json,                -- {summary,timeline,what_failed,why,contributing,mitigations,action_items}
    body_md, body_md_redacted,
    services_affected,          -- JSON array of entity IDs
    created_at, updated_at
)
```

---

## Tabletops (`/tabletops`)

Generate a runnable security exercise scoped to a service + threat,
then capture lessons.

### Flow

1. **Pick scope** — service ID + threat (STRIDE category or ATT&CK
   tactic) + optional scenario hook.
2. **Sonnet generates** via `prompts/tabletop_generator.md`:
   - 1-paragraph opening scenario the facilitator reads aloud.
   - 4-6 timed **injects** (each at +5min, +10min, etc.) with an
     `expected_response` field for the facilitator's eyes.
   - 3-5-sentence facilitation notes (time budget, roles, pitfalls).
   - 4-7-bullet evaluation rubric.
3. **Run the exercise** with your team.
4. **Capture lessons** — bulleted list + tags. Each bullet becomes a
   `lessons` row tagged for retrieval; the tabletop is marked `ran_at`.

> ⬜ **Screenshot placeholder**: tabletop scenario page with injects
> + facilitation notes.
>
> ![Tabletop scenario](../images/feature-tabletop.png)

### Schema

```sql
tabletops (
    id, scenario_md,
    scope_service_id,
    threat_kind,
    injects_json,           -- [{minute, inject, expected_response}]
    participants,
    ran_at, lessons_md,
    created_at
)
```

---

## On-call handoff brief (report kind `oncall_handoff`)

Per-service handoff brief for the engineer about to take the pager.
Generated on-demand from `/reports` or via subscription.

Output (one screen):

- **Open action items** — postmortem action items still open
  affecting this service (≤5, newest first).
- **Recent incidents** — one-line summaries from the last 30 days.
- **New threats** — threats added in the latest TM not present in
  prior versions.
- **Deploy freeze** — string if active, null if none.
- **On-call now** — who's currently on (from `on-call.csv` ingest).
- **Notes** — 2-3 sentences of context the next on-call should know.

Subscribe to weekly cadence and let the scheduler deliver it Sunday
PM ahead of Monday handoff.

---

## Weekly security digest (report kind `weekly_security_digest`)

Auto-subscribed on Day-14. Fires Monday morning during the digest
tick. Summarizes the past week across:

- New / changed entities
- Decisions made
- Threat models updated
- Postmortems published
- Open kanban items overdue
- Coverage gaps spotted

Plus a **one thing to focus this week** headline — the single
sentence the engineer should care most about.

> ⬜ **Screenshot placeholder**: a rendered weekly digest.
>
> ![Weekly security digest](../images/feature-weekly-digest.png)

---

## Auto pre-meeting briefs (scheduler hook)

The nightly 22:00 scheduler tick walks tomorrow's ICS-imported
meetings and auto-generates a `meeting_prep` brief for each (up to
5/day, rate-limited). The Today widget shows them under "Today's
briefs" so you don't have to remember to run them manually.

Configure the ICS watcher at Settings → Integrations to enable.
