# Threat models become living (Phase 12)

The biggest single AppSec unlock in Tank: threat models that **survive
architectural change**, plus a **decisions / accepted-risk log** that
captures the deliberate choices behind your security posture over time.

---

## Versioned threat models (`/threat-models`)

Each Service entity gets its own versioned threat model. When the
contributing chunks for a service change (new endpoint added to the
repo, new arch doc ingested, runbook updated), Tank detects "drift"
and prompts a regeneration. The regen prompt passes the previous TM
to Sonnet, which marks each prior threat as:

- **`still_valid`** — the threat still applies as written. Keep.
- **`updated`** — the threat still applies but details have shifted
  (scope expanded, control added that doesn't fully mitigate).
  Description gets refined; tagged back to the prior threat index.
- **`invalidated`** — the threat no longer applies (e.g., the
  integration was removed). Listed in
  `invalidated_prior_titles` and **not** included in the new
  version's threat list.
- **`new`** — genuinely new threats not present in the prior version.

### Drift detection

Each TM stores an `arch_snapshot_hash` — the sha256 over the set of
chunk IDs that fed into its generation. The drift detector
recomputes the current hash and surfaces services where the two
diverge. Drives the **`architecture_drift`** nudge.

### Workflow

```
/entities/<service-id>  → "Generate threat model (v2)" → first TM
…service evolves…
Today dashboard         → "architecture_drift" nudge appears
                       → click regenerate → TM v2 with state badges
/threat-models/<tm-id>  → view current; version history collapsed at bottom
```

> ⬜ **Screenshot placeholder**: threat model detail showing v2 with
> state badges (✓ still_valid, ↻ updated, 🆕 new, ✗ invalidated).
>
> ![Versioned threat model](../images/feature-threat-model-v2.png)

### Schema

```sql
threat_models (
    id, service_entity_id, version,
    title, body_md, body_md_redacted,
    threats_json,             -- frozen STRIDEThreat[] at gen time
    arch_snapshot_hash,
    generated_at,
    confirmed_by_user
)
UNIQUE(service_entity_id, version)
```

---

## Decisions log (`/decisions`)

A queryable record of every deliberate security choice. Four kinds:

| Kind | What it means | Example |
| --- | --- | --- |
| `design_choice` | A deliberate architectural choice | "Use mTLS between payments-api and identity-svc" |
| `accepted_risk` | Known weakness, deferred | "Webhook replay window: 5 min — acceptable for now" |
| `deferred_fix` | Recognized fix that's been postponed | "Rotate Stripe API keys quarterly — postponed to Q3" |
| `security_invariant` | Stated rule the team won't break | "No service stores PCI data outside pii-vault" |

### Lifecycle

Decisions have a `status`: `open` (default) → `withdrawn` |
`expired` | `reaffirmed`. Accepted risks and deferred fixes carry
an `expires_at` timestamp. A nudge fires 7 days before expiry;
one-click `reaffirm 90d` extends; `withdraw` closes.

### How they get created

Three paths:

1. **Manually** — `/decisions` → "+ add a decision" form. Source =
   `manual`.
2. **From a design review approval** — when you approve a DR,
   spawn one or more decisions tagged `source='design_review'`,
   linked back to the review. Carries the DR's scope_entity_ids
   automatically.
3. **Extracted from an ingested doc** — `POST /api/decisions/extract-from/<doc_id>`
   runs Sonnet over the doc's chunks looking for "we decided to…",
   "we accepted…", "we deferred…", "we agreed never to…" statements.
   Returns a `DecisionExtraction` payload the user confirms via
   notes-style diff before commit. Source = `extracted`.

> ⬜ **Screenshot placeholder**: decisions log filtered to
> `accepted_risk`, with one entry expiring soon.
>
> ![Decisions log](../images/feature-decisions-log.png)

### Schema

```sql
decisions (
    id, title, body_md, body_md_redacted,
    kind,           -- design_choice|accepted_risk|deferred_fix|security_invariant
    status,         -- open|withdrawn|expired|reaffirmed
    scope_entity_ids,  -- JSON array of entity IDs this decision affects
    rationale,
    expires_at,
    owner_entity_id,
    source,         -- manual|extracted|postmortem|design_review
    source_doc_id,
    created_at, updated_at
)
```

---

## Nudges this phase ships

- **`architecture_drift`** — A service's TM is older than its current
  arch hash. Suggest regenerate.
- **`decision_expiring`** — An accepted_risk or deferred_fix decision
  expires within 7 days.
- **`unaddressed_threat`** — A high-likelihood / high-impact threat
  in any TM has no `suggested_controls` AND no decision in its
  service's scope. Suggest opening a design review.

---

## Chat tools added

- **`get_threat_model(service_id|service_name)`** — Returns the
  latest TM as `{version, threats[], body_md_redacted,
  arch_snapshot_hash, generated_at}`. Use whenever the user asks
  about threats / risks for a specific service.
- **`find_decisions(kind?, status?, scope_entity_id?, limit?)`** —
  Filterable decisions query. Use for "why did we…" or "what did we
  decide about…" style questions.
- **`get_recent_decisions(days)`** — List decisions made in the last
  N days. Useful for digest-style queries.

---

## Cost & cadence guidance

- TM generation: ~$0.02-$0.05 per service (adaptive thinking on).
- TM regeneration (with prior in context): same cost; the prior gets
  cached on the second call within a session.
- Decision extraction from a doc: ~$0.01-$0.03.
- Recommended cadence: regenerate any TM whose drift nudge has fired.
  Don't proactively regenerate all TMs — it's noise.
