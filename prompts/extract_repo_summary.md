# Repo summary → entity extraction

You are looking at a structured summary of a source-code repository
(NOT the source code itself — that never leaves the user's machine).
The summary contains: language line counts, manifest contents,
Dockerfile, CI workflow paths, auth/secrets grep hits, CODEOWNERS,
README, ARCHITECTURE.md if any.

Extract entities and relationships from this summary using the same
schema as `extract_entities.md`.

## Special guidance for repo summaries

- Each repo is at least one `Repo` entity (`name` = repo dir name) and
  at least one `Service` entity (often same name).
- Edges to look for:
  - `Service depends_on Service` — service-to-service deps mentioned in
    README or architecture doc.
  - `Service stores_data_in DataStore` — Postgres/Redis/DynamoDB/etc.
    referenced in manifests or README.
  - `Service authenticates_via Vendor` — Okta/Auth0/OAuth0 references.
  - `Service integrates_with Vendor` — Stripe/Snowflake/Datadog/Sentry
    references (treat each as a Vendor).
  - `Service hosted_in CloudAccount` — AWS account IDs (likely
    redacted as `[AWS_ACCT_*]`) referenced in ECR/CI.
  - `Person owns Repo` — CODEOWNERS lines (may be redacted emails).
  - `Service exposes Endpoint` — public hostnames mentioned (likely
    redacted).
- Be liberal with confidence on entities found in manifests (high) and
  cautious for things inferred only from grep hits or comments (low).
- For Dockerfile hits: emit a `Service` and an attribute
  `attrs.runs_as_user` if a non-root USER is set; flag root in
  `description` if no USER directive exists.
- For CI hits: emit `Repo has_control "ci"` only if CI files exist.

## Output shape

Same as `extract_entities.md` — a `ChunkExtraction` JSON object.

Return ONLY the JSON object — no commentary, no markdown fences.
