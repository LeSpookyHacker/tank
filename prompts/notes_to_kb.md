# Notes → KB diff

The user dumped freewrite notes after a meeting or reading. Your job:
extract proposed entities, relationships, and facts that Tank should
ADD to the KB **once the user confirms**.

This is not auto-commit. The user reviews each item and accepts or
rejects in the UI. Lean toward being conservative — flag fewer, higher-
quality items rather than a flood of low-confidence ones.

## Output

A `NotesDiff` JSON object with:

- `new_entities`: list of `ExtractedEntity` objects.
- `new_relationships`: list of `ExtractedRelationship` objects.
- `facts`: list of free-form `{claim, about_entity?, evidence_quote?}`
  objects for things that don't fit the entity/edge model.

## Rules

- Use the same entity types and relationship kinds as the main
  extractor (see `extract_entities.md`).
- For each item, set `confidence` based on how directly the notes
  support it. Hearsay = low. Direct claim = high.
- `evidence_quote` should be a verbatim substring of the notes.
- If the notes mention someone the KB already has an entity for (you
  can infer from context if available), still emit the entity — the
  upsert layer will dedup.
- If notes say "Alice said X about Y", that's a `fact` (claim), not
  a relationship. Use facts for one-off statements that don't fit
  the typed graph.

## Style

- Placeholders stay verbatim.
- Don't speculate beyond the notes. If the user wrote "Alice mentioned
  Raj works on FinOps", don't infer Raj's reporting line.

Return ONLY the JSON object — no commentary, no markdown fences.
