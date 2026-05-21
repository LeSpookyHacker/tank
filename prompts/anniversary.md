# Anniversary retrospective

You're producing a retrospective at a tenure milestone (Day 30, 60,
90, 180, or 365). The scope block has the current state of the KB.
The user task says how many days in we are.

## Output

An `AnniversaryRetro` JSON object with:

- `day_n`: echo the day count.
- `what_you_built`: 3-6 bullet points. Real outputs visible in the
  KB (new entities added by the user, reports generated, follow-ups
  closed). NOT generic "you learned a lot."
- `what_you_learned`: 3-6 bullet points. Observations the KB now
  supports that it wouldn't have at Day 0.
- `what_drifted`: 1-5 bullet points. Things that have changed under
  you — stale runbooks, decisions that didn't land, services that
  churned past your last review.
- `next_30_days`: 3-5 priorities, concrete and sized.
- `summary`: 2-3 sentence executive summary.

## Style

- Be honest. A Day-30 retro that says "you've mastered the company"
  is worthless. Real retros surface what's NOT going well.
- Cite real KB evidence in the bullets — entity names, doc titles.
- Don't invent. If the KB doesn't show what was built, say so in
  `what_drifted` ("we don't track outcomes — worth adding").
- Tone matches the tenure milestone. Day 30 = "ramping up", Day 90 =
  "executing", Day 180+ = "ownership/maintenance".

Return ONLY the JSON object — no commentary, no markdown fences.
