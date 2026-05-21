# Extract decisions from a document

The user's document may contain explicit or implicit security
decisions:
- **design_choice** — a deliberate architectural choice ("we use mTLS
  between payments-api and identity-svc").
- **accepted_risk** — a known weakness the team chose not to fix yet
  ("we know webhook replays can occur within 5 min; we accept this
  for now").
- **deferred_fix** — a recognized fix that was postponed ("rotate
  Stripe API keys quarterly — postponed until Q3").
- **security_invariant** — a stated rule the team will not break
  ("no service stores PCI data outside the pii-vault").

## Rules

- **Only extract decisions actually stated in the document.** Do not
  infer. Do not paraphrase aspirations as decisions.
- **Each decision must have a one-sentence body + a kind.** If
  rationale is stated, include it; otherwise leave null.
- **`suggested_scope_entity_names`** — list the services / repos /
  data stores the decision applies to, exactly as named in the
  document.
- **`suggested_expires_days`** — for `accepted_risk` or
  `deferred_fix`, propose a review window (default 90 days). For
  `design_choice` or `security_invariant`, leave null (they don't
  expire).
- **Confidence** — your honest 0-1 score that this is a real
  decision (not a comment / aspirational statement).
- If the document contains no decisions, return `decisions: []`.

## Output

Return a `DecisionExtraction` payload.
