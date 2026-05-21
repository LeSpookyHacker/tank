# On-call handoff brief — per service

You are generating a one-screen on-call handoff for a single service.
The reader is the engineer about to take the pager for the next
rotation. They need the smallest set of facts that lets them respond
to a page tonight without surprise.

## Your job

Produce an `OnCallHandoff`:

1. **service_name** — exactly as named in scope.
2. **open_action_items** — postmortem action items still open that
   affect this service. Up to 5. Newest first.
3. **recent_incidents** — short one-line summaries of incidents in
   the last 30 days for this service. Up to 5.
4. **new_threats** — threats added in the latest TM version not
   present in prior versions. Up to 3.
5. **deploy_freeze** — string describing any active freeze relevant
   to this service. Null if none.
6. **on_call_now** — who's on now per on-call.csv. Null if unknown.
7. **notes** — 2-3 sentences of context the next on-call should
   know — recent changes, known flakiness, current ongoing
   issue. Honest about gaps.

## Rules

- Stay within scope. Don't pad with org-wide stats.
- If a section has nothing, return an empty list (or null for
  scalar fields). Do not invent.
- Be terse — this is a glance-sized brief.

## Output

Return an `OnCallHandoff`.
