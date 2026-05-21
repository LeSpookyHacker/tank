# Threat landscape report (STRIDE-ish)

You're producing a threat landscape for a single primary service named
in the user task. The scope block above contains:

- The primary service's entity card + linked redacted chunks.
- A global view of other entities for cross-reference.

## Your job

Produce a `ThreatLandscapeReport` JSON object with:

- `service_name`: name of the primary service.
- `threats`: list of `STRIDEThreat` objects. Aim for 4-8 high-signal
  threats covering different STRIDE categories. Prefer concrete
  exploitable issues over generic ones.
- `summary`: 2-3 sentences. What does the threat picture look like for
  this service?
- `blind_spots`: things the KB doesn't tell you that you'd want answered
  before being confident in this report.

## Per-threat rules

- `stride_category` must be one of: Spoofing, Tampering, Repudiation,
  InfoDisclosure, DoS, EoP.
- `description`: 2-3 sentences. Concrete attack path, not abstract.
- `likelihood` and `impact`: low | medium | high.
- `suggested_controls`: 1-3 specific mitigations.
- `evidence_chunk_ids`: list any chunk IDs from scope that anchor this
  threat. Empty list is allowed for derivable threats.

## Style

- Redaction placeholders stay verbatim (`[INTERNAL_HOST_007]` etc.).
- No speculation about what's behind a placeholder.
- Cite chunks by their real IDs from the scope block. Don't invent.

Return ONLY the JSON object — no commentary, no markdown fences.
