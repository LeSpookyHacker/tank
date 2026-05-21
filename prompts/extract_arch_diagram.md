# Architecture diagram extraction (vision)

You are looking at an architecture diagram from a security engineer's
employer corpus. Extract the entities (services, datastores, vendors,
people if labeled, cloud accounts) and the relationships between them
(arrows, edges, containment).

## Output

Return a JSON object matching this Pydantic shape:

```
DiagramExtraction {
  diagram_summary: <one paragraph, 3-5 sentences, in plain English>
  entities: [ExtractedEntity, ...]
  relationships: [ExtractedRelationship, ...]
}
```

`ExtractedEntity` and `ExtractedRelationship` follow the same schema as
the text-extraction prompt:

- Entity types: Service, Repo, Person, Endpoint, DataStore, CloudAccount,
  Vendor, Control, Policy, Runbook.
- Relationship kinds: depends_on, owns, reports_to, stores_data_in,
  authenticates_via, exposes, hosted_in, integrates_with, has_control.

## Rules

1. Use the labels visible in the diagram verbatim — don't translate or
   reformat them.
2. For arrows: source → destination is the natural direction
   (`A → B` becomes `src=A`, `dst=B`).
3. For containment (e.g. a service drawn inside a VPC box): emit
   `hosted_in` from the contained service to the container.
4. For protocol or label text on edges (e.g. "mTLS", "HTTPS"): put it
   in the edge's `attrs` (e.g. `{"protocol": "mTLS"}`).
5. If text on the diagram is illegible or ambiguous, lower the
   confidence (≤ 0.6); don't guess.
6. Names will likely contain redaction placeholders like
   `[INTERNAL_HOST_003]` — pass them through verbatim.
7. `diagram_summary` should make sense to a human who has not seen the
   diagram.

Return ONLY the JSON object — no commentary, no markdown fences.
