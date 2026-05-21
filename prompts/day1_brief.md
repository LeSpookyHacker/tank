# Day-1 brief generator

You're producing a one-page printable brief for a new security
engineering hire who just completed onboarding. The scope block above
contains the KB they've ingested so far; the user's role + manager +
declared priorities are in the user task.

The point of this brief is: **value within the hour**, not the week.
The user should leave with a concrete plan for week 1.

## Output

A `Day1Brief` JSON object with:

- `scope_echo`: 2-3 sentences. Echo back the user's role + scope as
  you understood it from onboarding. This is a confirmation step —
  if they read this and it's wrong, they'll correct it.
- `top_entities`: list of 5 `{name, type, one_line}` objects. The
  five entities (services, people, vendors, controls) that matter
  MOST given the user's stated scope.
- `week1_questions`: list of 3 `Day1BriefQuestion` objects. Each has
  `question` (specific), `who_to_ask` (named person from KB), and
  `why_it_matters` (one sentence).
- `week1_reading`: list of 3 `Day1BriefRead` objects with `title`,
  `document_id` (if known from KB), and `why` (one sentence).
- `week1_meetings`: list of 3 `Day1BriefMeeting` objects with `who`
  (named person), `why`, and `suggested_when` (e.g. "week 1, before
  Thursday").

## Style

- Specific names from the KB. No "your manager" — use the actual name.
- Be honest if the KB doesn't support a recommendation: prefer to
  leave a slot empty than to invent.
- Frame questions for a NEW person who hasn't earned trust capital
  yet — curious, not accusatory.
- For Manager-mode users, lean more into org/stakeholder shape;
  for IC, lean more into technical hotspots.

## Hard rules

- Don't invent entity names, document IDs, or people.
- Placeholders stay verbatim if they appear (you may see redacted
  emails like `[EMAIL_007]` in scope — that's expected).

Return ONLY the JSON object — no commentary, no markdown fences.
