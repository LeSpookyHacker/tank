# Security philosophy doc — user-driven refinement

You are updating an existing security philosophy doc based on free-form thoughts the
engineer has just written. Their text has been **locally redacted** (internal identifiers
replaced with placeholders) before reaching you — treat any `[REDACTED_*]` tokens as
opaque stand-ins for real names.

## Your job

Produce a fresh `PhilosophyDoc` that incorporates the user's thoughts:

- **Read the user's freewrite carefully.** Identify every distinct idea, stance, or lesson.
- **Map each idea to the existing doc:**
  - If it reinforces an existing stance → update `body_md` to reflect it (concisely).
  - If it contradicts an existing stance → revise or remove that stance.
  - If it is genuinely new → add a new `PhilosophyStance`.
  - If it is an unresolved question → add it to `open_questions`.
- **Keep stances that the user didn't touch.** Don't discard them.
- **Don't paraphrase the freewrite verbatim.** Distil it into stance language — concrete,
  opinionated, specific.

## Rules

- Don't pad. The doc is meant to be re-readable in 3 minutes.
- Avoid clichés ("shift left", "security is everyone's job"). Real stances are sharper.
- Be specific. If the user names a service, pattern, or practice, use it.
- If the freewrite contains no actionable new content, return the existing doc with only
  minor wording refinements.

## Output

Return a `PhilosophyDoc`.
