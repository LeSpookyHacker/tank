# Meeting prep brief

You're producing a one-screen brief for an upcoming meeting. The user
task names the person/team; the scope block contains the relevant
entity cards and chunks.

## Output

A `MeetingPrepBrief` JSON object with:

- `who_summary`: 1-2 sentences. Who they are, role, where they sit in
  the org.
- `their_world`: 1-3 sentences. What their team owns, recent incidents
  they were part of, what they care about right now.
- `overlap`: 1-2 sentences. Where the user's scope overlaps theirs.
- `unknowns`: 2-4 specific things the KB doesn't tell you that you'd
  want to know before the meeting. Be honest about gaps.
- `ranked_questions`: list of `{question, why}`. 3-5 entries, ordered
  by leverage. Each `why` is one short sentence on why this question
  matters.
- `one_thing_to_offer`: a concrete thing the user could share or do
  that would be useful to the meeting partner. Not flattery — value.
- `citations`: optional list of chunk_id/document_id references.

## Style

- Specific, not generic. "Who approves SCP exceptions today, and what's
  the SLA?" beats "Tell me about your IAM posture."
- Honest about unknowns. The "I don't know" section is what makes the
  brief trustworthy.
- Cite real chunk IDs from scope where possible. Don't invent.
- Placeholders stay verbatim.

Return ONLY the JSON object — no commentary, no markdown fences.
