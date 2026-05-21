# Coverage + visibility (Phase 14)

Tank knows your assets *and* your coverage. Three new ingest types
(Sigma detection rules, IAM policies, control frameworks) bring the
data in; four analyses synthesize it. Still strictly local —
everything redacts at ingest, every Sonnet call is over redacted text.

---

## Detection coverage (`/detections`)

Ingest Sigma YAML rules. Each rule becomes a `Detection` entity
linked to one or more `AttackTechnique` entities via the rule's
`attack.tXXXX` tags.

### Ingest

```bash
python -m scripts.ingest_cli ~/path/to/sigma-rules/ --category code
# or drop the directory into a folder watcher
```

The parser ([app/ingest/parsers/sigma.py](../../app/ingest/parsers/sigma.py))
extracts:

- `title`, `description`, `level`
- `tags` (incl. `attack.t1234` normalized to `T1234`)
- The raw YAML stays in the chunk for context

### Coverage map

`GET /api/detections/coverage` returns the matrix of Service ×
Technique × covering Detection names. Surfaces:

- "We detect lateral movement for payments-api ✓"
- "We don't detect credential access for identity-svc ✗"

> ⬜ **Screenshot placeholder**: detection coverage page showing
> covered vs uncovered techniques.
>
> ![Detection coverage](../images/feature-detection-coverage.png)

### Chat tool

`find_detection_for_technique(attack_id)` returns Detection entities
tagged with the given technique. Use when the user asks "do we
detect X?".

---

## ATT&CK mapping report (`attack_mapping`)

For every threat in every latest threat model, Sonnet assigns a
MITRE ATT&CK tactic + technique ID + technique name. Output is a
matrix:

| Service | Tactic | Technique | Exposure | Detections covering |
| --- | --- | --- | --- | --- |
| payments-api | credential-access | T1078 Valid Accounts | high | (none — gap) |
| identity-svc | initial-access | T1190 Public-Facing App | medium | "Auth0 anomaly", … |
| webhook-router | lateral-movement | T1021 Remote Services | low | … |

`top_gaps` lists the high/medium-exposure mappings with **no
covering detection**. Run monthly. Subscribe to it on a 28-day
cadence if you want diffs.

> ⬜ **Screenshot placeholder**: ATT&CK mapping report rendered.
>
> ![ATT&CK mapping](../images/feature-attack-mapping.png)

---

## IAM policy translator + audit

### Ingest

AWS IAM JSON, K8s RBAC YAML, GCP IAM bindings all flow through the
same content-sniffing parser ([app/ingest/parsers/iam.py](../../app/ingest/parsers/iam.py)).
At ingest time the parser computes a coarse 0-10 **risk score** and
a list of **callouts**:

- Wildcard actions (`*`, `service:*`)
- Wildcard resources (`*` or trailing `:*`)
- Sensitive actions (`iam:PassRole`, `sts:AssumeRole`,
  `kms:Decrypt`) without conditions
- Anonymous principal (`*` or `AWS:*` in trust policies)
- K8s ClusterRole with wildcard verbs / resources / secret reads
- GCP roles/owner, roles/editor, or `allUsers` bindings

Each policy becomes an `IAMPolicy` entity with these in `attrs_json`.

### Translator

`GET /api/iam/explain/<policy_id>` runs Sonnet over the policy with
the parsed callouts as context. Output: 250-word markdown explaining
**what this policy grants**, **risk callouts in user-facing terms**,
and **2-3 suggested follow-ups** — specific, not generic.

> ⬜ **Screenshot placeholder**: IAM policy explained.
>
> ![IAM policy translator](../images/feature-iam-translator.png)

Also exposed as a chat tool — `find_iam_risks(limit)` returns the
top-N IAMPolicy entities ranked by `risk_score`.

### Audit report

The `iam_audit` report kind runs `find_risks()` + Sonnet over the
top-50 policies, returning an `IAMAuditReport`:

- `policies` — per-policy: name, score, callouts,
  2-3-sentence contextualized explanation.
- `top_risks` — policy names with score ≥ 7.0.
- `summary` — overall posture (2 sentences).

---

## Compliance evidence collection (`/compliance`)

Ingest a control framework JSON dump (CIS Controls v8, NIST 800-53,
SOC2 CC, or anything with `[{id, title, description, family}]`
shape). Each control becomes a `Control` entity.

Then `POST /api/compliance/collect-evidence` iterates every Control
entity and hybrid-searches the KB for matching docs / decisions /
policies / runbooks / threat models. Matches go into the
`compliance_evidence` table with a confidence score.

The page shows the gap report: controls with no evidence.

> ⬜ **Screenshot placeholder**: compliance page showing controls and
> gap badges.
>
> ![Compliance gaps](../images/feature-compliance.png)

### Chat tool

`find_evidence_for_control(control_id)` returns the evidence rows
mapped to that control. Used for audit-prep questions.

### Schema

```sql
compliance_evidence (
    control_id, evidence_kind, evidence_id,
    confidence, captured_at,
    PRIMARY KEY (control_id, evidence_kind, evidence_id)
)
```

---

## Attack-surface ledger (`/attack-surface`)

Weekly snapshot of all Endpoint entities + their attrs, diffed
against the prior snapshot.

### Cadence

- Auto-fires Sunday 09:00 from the scheduler.
- Manual via `POST /api/attack-surface/snapshot`.

Each snapshot stores:

- `endpoints_json` — full Endpoint entity dump at capture time.
- `summary_md` — diff vs the prior snapshot (added / removed counts,
  plus a one-line headline).

### What it catches

- New external endpoints exposed since last week.
- Endpoints removed (deprecation visibility).
- Total exposure trend.

> ⬜ **Screenshot placeholder**: attack-surface page with latest
> snapshot + history.
>
> ![Attack surface](../images/feature-attack-surface.png)

### Schema

```sql
attack_surface_snapshots (
    id, snapshot_at,
    endpoints_json,
    summary_md
)
```

---

## Cost & cadence

- Sigma rule ingest: $0.001-$0.005 per rule (extraction).
- IAM policy ingest: free at ingest (parser only); $0.01-$0.02 per
  Sonnet `explain()`.
- `iam_audit` report: $0.05-$0.10 (limited to top-50 policies).
- `attack_mapping` report: ~$0.10 (one Sonnet call per TM).
- Compliance evidence collection: scales with framework size. CIS
  Controls v8 (~18 controls) → $0.10-$0.30 per full run. Run monthly.

---

## New entity types (Phase 14)

| Type | What | Provenance |
| --- | --- | --- |
| `Detection` | A Sigma rule | `source` from ingest |
| `AttackTechnique` | A MITRE technique referenced in a Detection or threat | `inferred` from tag parsing |
| `IAMPolicy` | An AWS/K8s/GCP policy doc | `source` from ingest |
| `Asset` | Generic placeholder for non-service objects (LBs, S3 buckets, certs, DNS) | varies |
