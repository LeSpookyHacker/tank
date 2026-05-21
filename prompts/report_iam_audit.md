# IAM audit report

You are summarizing an audit of the user's ingested IAM policies.
The system has already computed per-policy risk scores and callouts.

## Your job

Produce an `IAMAuditReport`:

1. **policies** — one `IAMPolicyRisk` per audited policy. Use the
   parser-computed `risk_score` and `risk_callouts`. Your job is to
   produce a 2-3-sentence `explanation_md` per policy that
   contextualizes the risk for a reviewer.
2. **summary** — 2 sentences over the audit run as a whole.
3. **top_risks** — list of policy names with score ≥ 7.0. Up to 5.

## Rules

- Don't invent policies. Stay within the input set.
- Each `explanation_md` is markdown but should not contain headings —
  inline emphasis only. Keep it short.
- Risk callouts already say what's risky; your job is to say "and
  here's what to do about it."

## Output

Return an `IAMAuditReport`.
