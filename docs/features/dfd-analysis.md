# DFD Threat Modeling

Automated STRIDE threat modeling delivered through a three-stage pipeline:
four input modes → 4-step progress tracker → split-panel interactive workspace.

---

## Getting started

- **Sidebar** → Pipeline → **DFD Analysis**
- **Ingest page** → scroll to the bottom → *"Have a Data Flow Diagram? Analyze
  it with STRIDE threat modeling →"*

---

## Stage 1 — Input

Four tabs let you get a diagram into Tank in whichever way fits your workflow.

### Tab A: Paste Mermaid

Type or paste Mermaid source directly. Tank accepts `graph TD`, `graph LR`,
and `flowchart` variants. A live preview renders below the editor (300 ms
debounce) — invalid syntax shows an inline error without losing your text.

Click **Load example** to populate a 6–8 node reference DFD (browser → ALB →
API Gateway → Auth Service → PostgreSQL + Redis + S3, with internet/VPC trust
boundary subgraphs).

### Tab B: Upload file

Drag-and-drop or click to browse:

| Extension | Behavior |
| --- | --- |
| `.mmd`, `.txt` | Content placed in Tab A; switches to Tab A automatically |
| `.png`, `.jpg`, `.jpeg`, `.svg` | Thumbnail preview; submitted as image for Claude Vision analysis |
| `.json` | Formatted preview shown inline |

Images are analyzed by Claude Vision — results may vary with low-resolution or
stylized diagrams.

### Tab C: From document

Upload a PDF, DOCX, TXT, or Markdown architecture document. Tank extracts the
text locally (`pypdf` / `python-docx`), sends it to Claude, and generates a
Mermaid DFD. The result appears in Tab A with a "Review before analyzing" notice
— inspect and edit before running STRIDE.

### Tab D: From description

Paste a plain-language description of your system (services, data flows, trust
boundaries). Claude generates Mermaid source and populates Tab A for review.
Example prompt format accepted:

> "A browser talks to an ALB. The ALB forwards to an API server which reads
> from PostgreSQL and writes session tokens to Redis. A cron job exports to S3."

---

## Stage 2 — Progress tracker

Once you submit, the input form hides and a 4-step tracker takes over:

```
✓  Parsing diagram
⟳  Identifying system components   ← spinning while Claude is running
   Mapping attack surfaces
   Generating threat model
```

Analysis typically takes 20–40 seconds. Progress is driven by a Server-Sent
Events stream (`GET /api/dfd/task/{task_id}/stream`). On error, a red step and
message appear with a **Try again** button that returns to Stage 1.

---

## Stage 3 — Interactive workspace

### Header bar

| Control | Function |
| --- | --- |
| ⚡ Loaded from cache | Shown when the result was served from the SHA-256 cache; no API cost was incurred |
| ↺ Run again | Bypasses cache (`force=true`), re-runs STRIDE, returns to Stage 2 |
| Export menu | PDF / Annotated .mmd / Original .mmd / JSON |
| Metadata | Input format + analysis date |

### Split panel

Left panel (55% default) holds the diagram; right panel (45%) holds the
findings. Drag the divider between them to resize. Each panel scrolls
independently within the viewport.

### Diagram panel

The annotated Mermaid diagram is rendered with a custom Nyx theme:

- Background `#0d0d12`, primary color `#1a1728`, line color `#6c5ce7`
- Nodes are color-coded by their highest-severity threat

**Interaction:**
- **Hover node** — tooltip shows element label and threat count
- **Click node** — filters the findings panel to threats on that element;
  a "Showing threats for: X · Clear ×" chip appears above the cards
- **Click empty space** or press **Escape** — clears selection, restores all cards
- **Zoom** — `+` / `−` buttons or scroll wheel; CSS `transform: scale()`

### Findings panel

**Summary strip** — severity chips with counts: Critical / High / Medium / Low.

**Filter toolbar** — severity pill toggles and STRIDE category pill toggles.
Cards animate in/out on toggle. "Clear all" resets both groups.

**Threat cards** — one per identified threat, sorted Critical → Low:

```
[High] [Spoofing]  Token forgery via weak signing key
Auth Service  ·  CVSS ~7.5
"An attacker could forge JWT tokens..."  [Read more ▾]

[▸ Mitigation]  (collapsed by default; click to expand)
[OWASP A02:2021]  [CWE-347]        [Highlight in diagram →]
```

**"Highlight in diagram →"** — selects the threat's node in the diagram panel,
centering the interaction back on the diagram.

---

## Threat fields

| Field | Description |
| --- | --- |
| `threat_id` | Sequential ID (T001, T002, …) |
| `title` | Short threat title |
| `stride_category` | Spoofing / Tampering / Repudiation / Information Disclosure / Denial of Service / Elevation of Privilege |
| `element_id` | Mermaid node identifier |
| `element_label` | Human-readable element name |
| `severity` | Critical / High / Medium / Low |
| `cvss_estimate` | Approximate CVSS 3.x base score (float) |
| `description` | 1–2 sentence threat description |
| `mitigation` | Concrete, element-specific remediation |
| `references` | OWASP / CWE identifiers |

### Severity rubric

| Severity | Color | Meaning |
| --- | --- | --- |
| **Critical** | `#DC2626` | Direct RCE, full data exfiltration, or auth bypass with no prerequisites |
| **High** | `#EA580C` | Auth bypass or privilege escalation requiring attacker preconditions |
| **Medium** | `#D97706` | Data leakage, indirect escalation, or significant functionality disruption |
| **Low** | `#4F46E5` | Defense-in-depth gap, low-likelihood scenario, or informational |

---

## Working with incomplete diagrams

The **✦ Improve diagram** button (on any result page) sends your diagram through
Tank's knowledge base:

1. Runs a semantic search over ingested architecture docs for services, trust
   boundaries, and data flows.
2. Claude receives both the incomplete diagram and KB context, then produces a
   more complete Mermaid source.
3. A bullet list shows what was added (new nodes, missing data stores, unlabeled
   trust boundaries, etc.).
4. Click **Run STRIDE on improved diagram** to immediately threat-model the
   result, or **Copy Mermaid** to take the improved source elsewhere.

Ingest your architecture docs before using Improve for the best results.

---

## Caching and re-analysis

Every analysis is stored in the `dfd_analyses` table keyed by SHA-256 of the
input. Re-submitting the same diagram returns the cached result instantly at
zero API cost. The **⚡ Loaded from cache** badge makes this visible.

**↺ Run again** bypasses the cache. Use it after:

- Updating `prompts/dfd_stride.md`
- Ingesting new architecture docs that change the threat picture
- Modifying the diagram and wanting a clean result

---

## Exports

| Option | Content |
| --- | --- |
| **Print / Save as PDF** | `window.print()` with professional `@print` CSS — cover page, full-width diagram, threat table (all fields), STRIDE coverage matrix (6 categories × 4 severities), Mermaid source appendix |
| **Annotated .mmd** | Mermaid source with `style` directives that color-code nodes by severity |
| **Original .mmd** | Unmodified input source as submitted |
| **JSON** | Metadata wrapper (`dfd_id`, `analyzed_at`, `input_format`, `total_threats`, severity summary) + `elements` + full `threats` array |

---

## Project context

Select an active project before running analysis. If a project is active and has
notes, Tank injects those notes into the STRIDE prompt so threats are specific
to your system rather than generic. Project scope is stored with the analysis in
`dfd_analyses.project_id`.

---

## Privacy

DFD text and images follow the same privacy pipeline as all other Tank inputs:

- **Mermaid source / document text / description**: passed through
  `apply_redactions` before being sent to Claude. Internal hostnames, emails,
  IPs, and secrets in node labels or edge text are replaced with placeholders.
- **Images**: sent to Claude Vision; any extractable text is redacted first.
  The vision response is rehydrated before display.
- Results are stored in redacted form; the `redaction_map` is local-only.
