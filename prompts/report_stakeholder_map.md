# Stakeholder map

Build a stakeholder map from the People + reports_to + owns edges in
scope. This is most useful for Manager-mode users but everyone needs
to know who's who.

## Output

A `StakeholderMap` JSON object with:

- `critical`: people the user must work with regularly (their direct
  stakeholders + frequent collaborators).
- `frequent`: people they'll interact with weekly-ish.
- `situational`: people who come up only in specific contexts.
- `first_30_day_intros`: prioritized list of suggested intro chats.
- `summary`: 2-3 sentences. What's the org's shape? Where's the
  political gravity?

## StakeholderTier rules

- `name`: real name from the entity scope (placeholder if redacted).
- `role`: their title / function.
- `overlap_areas`: 1-3 areas where the user's scope overlaps theirs.
- `suggested_first_conversation`: a concrete topic or question to open
  with.

## Style

- Don't make up people. Use names from the entity scope.
- "Critical" is for ~3-7 people. Beyond that and it's not critical.
- The user's manager, if discernible, is critical.
- The first-30-day intros list should be ordered by priority.

Return ONLY the JSON object — no commentary, no markdown fences.
