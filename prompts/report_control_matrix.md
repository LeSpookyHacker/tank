# Control coverage matrix

Build a matrix of services × controls showing which services have
which controls in place.

## Controls to check (default set)

`sso`, `mfa`, `secrets_mgmt`, `vuln_mgmt`, `ir_runbook`, `on_call`,
`dr_tested`, `threat_model_on_file`.

You can extend with 1-2 additional controls if the KB strongly
suggests one matters (e.g. `customer_data_audit_log` for any service
touching PII).

## Output

A `ControlMatrix` JSON object:

- `rows`: one `ControlMatrixRow` per Service entity in scope.
- `controls_checked`: the list of control names you actually checked
  (typically the default set).
- `summary`: 2-3 sentences. What's the headline? Which controls have
  the worst coverage?

## ControlMatrixRow rules

- `service_name`: name from the entity scope.
- `service_id`: matching entity ID.
- `controls`: dict mapping each control name → one of:
  - `yes`: KB shows the control is implemented.
  - `partial`: implemented for some paths, not all (e.g. SSO for
    employees but not all customer-facing flows).
  - `no`: KB shows the control is absent.
  - `unknown`: KB doesn't say either way.
- `evidence_chunk_ids`: chunk IDs from scope that anchor the `yes`
  or `no` cells. Optional but encouraged.

## Style

- When in doubt, choose `unknown` over `yes`. "Mentioned in passing"
  is not implementation evidence.
- All rows in `rows` should reference real Service entities from the
  scope block. Don't invent.
- Don't repeat the same control name with different spellings; use
  the underscore_separated form everywhere.

Return ONLY the JSON object — no commentary, no markdown fences.
