# Chat + the original six reports

Tank's foundational synthesis surfaces: chat over your KB and six
report kinds that get re-runnable across your tenure.

---

## Chat

Tank's chat is available two ways:

**Side panel** — a persistent panel pinned to the right of every page
(except `/chat` and `/onboarding`, where it's suppressed). Collapsible
to a "Chat ▰" pill, resizable by dragging the left edge (240–600px),
and the conversation is preserved in `localStorage` across navigation.
Click "⤢" in the panel header to jump to the full-screen chat with the
same conversation.

**Full-screen** (`/chat`) — dedicated chat page for longer sessions.
The side panel is hidden here since the page IS the chat.

Both surfaces use the same streaming chat interface with full tool use.
The chat loop sees your KB through 15 tools (see below); Sonnet picks
which to call.

### What makes it work

- **Hybrid retrieval**: sqlite-vec ANN over local embeddings + FTS5
  BM25, fused via reciprocal rank fusion. Falls back to FTS-only if
  sqlite-vec isn't loaded.
- **Prompt caching**: two cache breakpoints per turn — after the
  system prompt (~2k tokens, stable per role mode) and after the KB
  context block (~10-40k tokens). Multi-turn conversations and
  multi-report runs reuse the cache for ~2× cost reduction.
- **Tool use loop**: text deltas stream via SSE; `tool_use` blocks
  pause the stream, execute locally, and continue with the result
  appended. Iterates until `end_turn`.
- **Tenure lens**: the system prompt loads `chat_lens_<lens>.md`
  based on `current_lens()` — same KB, different framing depending
  on whether you're in map / prioritize / execute / maintain mode.
- **Citations**: every assistant answer carries `citations_json` with
  chunk_id + document_id + section_path + snippet. The UI renders
  them as clickable pills.

> ⬜ **Screenshot placeholder**: a chat exchange with tool-use trace
> expanded and citations visible.
>
> ![Chat with tool use](../images/feature-chat-tools.png)

### The 15 chat tools

Defined in [app/kb/tools.py](../../app/kb/tools.py).

| Tool | Input | Purpose |
| --- | --- | --- |
| `search_kb` | query, type_filter?, top_k? | Hybrid retrieval over redacted chunks |
| `get_entity` | entity_id OR (type, name) | Full entity card + linked chunks |
| `list_relationships` | entity_id, direction, kind? | Outgoing/incoming edges |
| `find_control_gaps` | control, scope_entity_ids? | Services lacking a given control |
| `list_entities` | type, limit, offset | Paginated by type |
| `get_document` | document_id, include_chunks? | Doc metadata + optional chunks |
| `get_threat_model` | service_id OR service_name | Latest TM for a service |
| `find_decisions` | kind?, status?, scope_entity_id?, limit? | Filtered decisions log query |
| `get_recent_decisions` | days | "What's been decided lately" |
| `find_detection_for_technique` | attack_id | Detections covering an ATT&CK technique |
| `find_iam_risks` | limit | Top-N IAMPolicy entities by risk score |
| `find_evidence_for_control` | control_id | Compliance evidence map lookup |
| `search_lessons` | query, tag? | Past lessons by free-text + tag |
| `get_risk_register` | category?, treatment?, limit? | Open risks ordered by residual score |
| `find_ir_runbooks` | service_name?, service_id?, limit? | IR runbooks for a service |

### Behavior knobs

- **Forking on role-mode switch**: switching IC ↔ Manager mid-thread
  creates a new conversation, preserving the original. Audit-friendly.
- **"This was wrong"** affordance: on every assistant message, flag
  the response. Goes into `notes` with `provenance='user'` and
  optionally disputes the offending entity attr.
- **Reconnect-safe SSE**: each subscriber gets its own queue; closing
  the tab cleans up immediately. Multi-tab open on the same
  conversation works — both tabs receive every event.

### Cost guidance

- A typical chat turn: $0.005-$0.02 depending on KB context size.
- Daily chat use over a tenure: ~$0.50/day on average.
- Hot-cache turns (immediate follow-ups in the same conversation):
  ~50-70% cheaper.

---

## Report kinds (14 total)

All use Sonnet 4.6 with `thinking={"type": "adaptive"}` and share
the cached scope block. Generated from `/reports` or via subscription.

### Report rendering and export

Report detail pages render the Markdown output with full formatting (headings,
tables, code blocks, lists) via `marked.js`. From any report detail page:

| Button | Action |
| --- | --- |
| ↓ PDF | `window.print()` — browser print dialog with nav/sidebar hidden via `@media print` |
| ↓ Markdown | Downloads the raw `.md` source |

### Scoped reports — entity picker

`threat_landscape` and `questions_for_team` require a scope selection.
Clicking **Generate** opens a searchable `<dialog>` modal that fetches
entities from `/api/entities`:

- **Threat landscape** — lists `Service` entities; the selected entity's
  `id` is sent as `scope.service_id`.
- **Questions for team** — lists `Person` and `Team` entities combined;
  the selected entity's `name` is sent as `scope.team_or_person`.

The modal can be dismissed with the **×** button, clicking the backdrop,
or pressing **Escape**.

### `threat_landscape` — STRIDE per service

One-shot threat list for a single service. Superseded by the Phase-12
versioned threat models for ongoing use, but still useful for a quick
one-off. Output: STRIDE category × title × likelihood × impact ×
suggested controls × evidence chunks.

### `cross_service_gaps`

Patterns spanning multiple services — coverage gaps, blind spots,
architectural risks that no single TM would surface. Output:
`gap (pattern, severity, affected entities, evidence)` list +
blind-spots list.

### `oncall_handoff`

A rotation-handoff brief for the incoming on-call primary responder.
Output: open incidents, recent service changes, top risk areas to
watch, and contacts for each affected service. Scoped to a specific
on-call rotation if one is provided, otherwise KB-wide.

### `plan_30_60_90`

Trust-building / coalition / execute ladder. Output: per-window
list of `(title, why, who_to_talk_to, estimated_effort, success_signal)`.

### `stakeholder_map` — Manager-flavored

Tiered relationship map: critical / frequent / situational. Each
tier: name, role, overlap areas, suggested first conversation.
Plus a `first_30_day_intros` list.

### `questions_for_team`

Ranked question lists for talking to a team or person. Output:
must_ask / should_ask / nice_to_ask / red_flags_to_probe.

### `control_matrix`

Service × control coverage matrix. Default control set: SSO, MFA,
secrets_mgmt, vuln_mgmt, IR_runbook, on_call, DR_tested,
threat_model_on_file. Add 1-2 custom controls per scope.

> ⬜ **Screenshot placeholder**: control matrix rendered.
>
> ![Control matrix](../images/feature-control-matrix.png)

### `weekly_security_digest`

A weekly aggregate of security activity across the KB: new threats
found, decisions made, vulnerabilities opened/closed, drift detected,
postmortems published. Scheduled automatically via subscriptions.
The digest diff on the report detail page shows what changed since
the prior week.

### `attack_mapping`

MITRE ATT&CK technique coverage analysis. Maps ingested detection
rules (Sigma, custom SAST) to ATT&CK techniques; identifies
techniques with no coverage. See also
[features/coverage-visibility.md](coverage-visibility.md).

### `iam_audit`

Reviews IAM policies ingested as `IAMPolicy` entities and surfaces
risky patterns: wildcard roles, excessive permissions, missing
conditions, over-broad service accounts. Pairs with the IAM
translator for detailed per-policy analysis.

### `risk_register`

Generates a heat-map narrative from all open risks — inherent vs
residual score distribution, top risks by residual score, control
coverage by risk category. Uses the `risks` table; pairs with the
security program dashboard for leadership reporting.

### `state_of_security`

A concise snapshot of the overall security posture: what's covered,
what's not, top open risks, compliance status, and a one-paragraph
executive summary. Good for a monthly status email.

### `initial_assessment`

A structured first-90-days security readiness assessment: coverage
by domain (identity, network, data, SDLC, detection), key findings,
quick wins, and a prioritized roadmap. Generated once at program
start; can be regenerated at any time.

### `program_roadmap`

A strategic 6–12 month security program roadmap tailored to your KB,
compliance targets, and open risks. Output: phased initiatives, per-phase
milestones, resource estimates, and sequencing rationale.

---

## Subscriptions

Any report kind can be subscribed to on a daily / weekly / monthly /
quarterly cadence. The scheduler dispatches due subscriptions during
the morning digest. The detail page shows a diff against the prior
run when a new one lands — so `cross_service_gaps` subscribed weekly
gives you a "what changed in our risk posture this week" stream.

Manage at `/reports` → "Subscriptions" tab.
