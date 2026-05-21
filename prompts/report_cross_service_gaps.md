# Cross-service gaps & blind spots report

Look across all services in scope and identify **patterns** of risk
or missing controls that span more than one entity.

## Output

A `CrossServiceGapsReport` JSON object with:

- `gaps`: list of `Gap` objects. Each describes a pattern, the
  services affected, severity, and evidence.
- `blind_spots`: things the KB doesn't tell you that you'd want
  answered before being confident.
- `summary`: 2-3 sentences. What's the headline pattern across
  these gaps?

## Gap rules

- `pattern`: short label, e.g. "Tier-1 services with no postmortem on
  file" or "Services using long-lived AWS access keys".
- `affected_entity_names`: human-readable names from scope.
- `affected_entity_ids`: corresponding IDs from scope.
- `severity`: low | medium | high | critical.
- `notes`: 2-4 sentences explaining the gap and why it matters
  *organizationally* (not just technically).
- `evidence_chunk_ids`: chunk IDs from scope that anchor this finding.

## Style

- Aim for 4-8 gaps. Quality > quantity. Don't pad.
- A "gap" affecting only 1 service isn't really cross-service — fold
  it into a broader pattern or omit.
- Cite real chunk IDs from scope. Don't invent.

Return ONLY the JSON object — no commentary, no markdown fences.
