# Questions for a team or person

Produce a ranked question list for the user to bring into a 1:1 or
team meeting with whoever the user task names.

## Output

A `QuestionList` JSON object with:

- `team_or_person`: echo back the name from the user task.
- `must_ask`: 3-5 questions the user shouldn't leave the meeting
  without asking.
- `should_ask`: 3-5 second-tier questions.
- `nice_to_ask`: 2-4 lower-priority but interesting questions.
- `red_flags_to_probe`: 1-3 things in the KB that look concerning
  about this team/person; questions that surface those concerns
  diplomatically.

## Style per question

- Specific, not generic. "What's the SLA on customer key rotation?"
  beats "How do you handle security?"
- Reference entities from scope where helpful — but the questions
  should make sense even without them.
- Phrase as questions, not statements. End with `?`.
- Don't ask things the KB already answers (waste of meeting time).

## Tone

- Curious, not accusatory. The user is new; they're learning.
- Where the KB shows a gap, frame as "how do you currently…" not
  "why isn't…".

Return ONLY the JSON object — no commentary, no markdown fences.
