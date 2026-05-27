# Core Concepts

Before using Tank day-to-day, it helps to understand a few key building blocks. This page explains the mental model, not the implementation — for internals, see [architecture.md](architecture.md).

---

## What Tank is (and is not)

**Tank is a local knowledge base with an AI interface.** You give it your employer's documents and repos; it extracts structured knowledge, stores everything locally, and uses Claude to reason over it in response to your questions.

**Tank is not:**
- A search engine. It retrieves context and reasons over it — the answer is synthesized, not quoted verbatim.
- A cloud service. Everything runs on your machine. Nothing is stored remotely except your requests to the Anthropic API (which are redacted first).
- A threat database. Its knowledge comes entirely from what you ingest. If you haven't ingested a doc, Tank doesn't know about it.
- A replacement for judgment. Its output is grounded analysis, not ground truth. You decide what to act on.

---

## The five building blocks

### 1. Documents

A document is any file you ingest into Tank — a PDF architecture overview, a Markdown runbook, a CSV CMDB export, a GitHub repo, a Sigma detection rule, an IAM policy JSON, a screenshot of a diagram. Tank parses it, breaks it into chunks, redacts sensitive identifiers, embeds the chunks locally, and stores everything in SQLite.

You can ingest documents via the web UI (Settings → Ingest) or from the CLI:

```bash
python -m scripts.ingest_cli path/to/doc.pdf --category architecture
```

Supported categories: `architecture`, `code`, `cmdb`, `people_process`, `runbook`, `postmortem`, `detection`, `iam`, `control_framework`.

### 2. Entities

When Tank processes a document, it extracts **entities** — the named things your company cares about. Tank recognizes 14 entity kinds:

| Kind | Examples |
|------|---------|
| Service | payments-api, auth-service, pii-vault |
| Repo | payments-api (GitHub), webhook-router |
| Person | Jordan Lee (VP Eng), Mei Watanabe |
| DataStore | prod-db, redis-cache, audit-logs-s3 |
| Vendor | Stripe, Datadog, PagerDuty |
| Control | MFA enforcement, TLS-everywhere, least-privilege |
| Policy | secrets-management-policy, data-classification-policy |
| Runbook | pii-breach-response, service-restart |
| IAMPolicy | analytics-cross-account-role, k8s-rbac-pii-vault |
| Detection | helix-ec2-metadata-ssrf (Sigma rule) |
| ATT&CKTechnique | T1552.005 (Cloud Instance Metadata API) |
| Threat | spoofing-auth-token, tampering-payment-data |
| Risk | (formal risk register entries) |
| Vulnerability | (findings from Nyx or manual entry) |

Entities are connected by **relationships**: `depends_on`, `has_control`, `covered_by`, `owns`, `maps_to`, and others. The resulting graph is what the chat tools navigate.

Each entity carries a **provenance badge** that tells you how confident Tank is:

| Badge | Meaning |
|-------|---------|
| `source` | Explicitly stated in an ingested document |
| `inferred` | Claude concluded it from context |
| `claim` | Stated but unverified |
| `user` | You added it manually |

You can see and correct entities in **Knowledge Base → Entities**.

### 3. Chunks

A chunk is a small piece of a document — typically 800 tokens — that Tank uses as a unit of retrieval. When you ask Tank something, it finds the most relevant chunks and sends them to Claude as context.

Chunks are stored in two forms:
- `text_original` — the raw text, kept locally for forensics. Never leaves your machine.
- `text_redacted` — the version with sensitive identifiers replaced by placeholders. This is what goes to Claude.

You don't interact with chunks directly, but they explain why Tank sometimes can't answer a question: if the relevant doc hasn't been ingested, there are no chunks for it.

### 4. Projects

A project is a compartment that groups related documents, conversations, threat models, reports, and workstream artifacts under a single label.

**Example uses:**
- One project per major initiative ("Auth Hardening Q2 2026")
- One project per service scope ("PII Vault security review")
- One project per compliance sprint ("SOC 2 Evidence Q3")

When you work inside a project, the project's notes are injected into every chat system prompt, giving Claude context about the project's goals and constraints. Documents ingested into a project are scoped to it — global chat draws from everything; project chat draws from the project's slice.

Switch between projects from the top-right project selector.

### 5. The Lens

Your **lens** is Tank's framing of where you are in your tenure. It shifts automatically based on when you told Tank you started:

| Lens | When | Focus |
|------|------|-------|
| **Map** | Days 1–30 | Understand the terrain: who owns what, where the risk lives, who to talk to |
| **Prioritize** | Days 31–60 | Rank what matters: which threats are highest risk, which gaps are most exposed |
| **Execute** | Days 61–90 | Act on the priorities: ship threat models, author design reviews, drive remediations |
| **Maintain** | Day 91+ | Sustain: keep artifacts current, track decisions, run recurring operations |

The lens affects chat phrasing, report emphasis, and which nudges surface. Same KB — different frame.

You can see your current lens on the home dashboard and override it in Settings if your onboarding is moving faster or slower than the default timeline.

---

## Nudges vs. Follow-ups

These are easy to confuse because they both appear on the home dashboard.

**Nudges** are scheduler-generated insight cards. Tank creates them automatically — a decision about to expire, a threat model that has drifted, a service with a high-severity threat but no IR runbook. They are informational: read it, decide what to do, mark it dismissed.

**Follow-ups** are action items you (or Tank) create deliberately. They have a due date and a status (`open`, `done`). They persist until you mark them done. Tank can auto-create follow-ups when you publish a postmortem (one per action item) or complete an onboarding step.

Think of nudges as Tank tapping your shoulder. Follow-ups are your todo list.

---

## The knowledge flow

Here is the lifecycle of information through Tank, from document to Claude response:

```
Your doc (PDF / repo / Sigma rule / …)
    │
    ▼ parse
Extracted text
    │
    ▼ chunk (800 tokens, 120-token overlap)
Text chunks
    │
    ▼ redact  ◄── redaction_map stored locally (original ↔ placeholder)
Redacted chunks
    │
    ▼ embed (local sentence-transformers, no network)
Vector + FTS5 index (SQLite)
    │
    ▼  … later, when you ask a question …
    │
    ▼ hybrid retrieve (vector ANN + BM25 keyword, reciprocal rank fusion)
Top-k relevant chunks (already redacted)
    │
    ▼ assemble prompt (cached system + cached KB block + history)
    │
    ▼  ──── Anthropic API (redacted text only) ────►
    │                                              │
    │                                        Claude's response
    │                                              │
    ▼  ◄────────────────────────────────────────────
Rehydrate (placeholders → originals, using local map)
    │
    ▼
Display view (what you see in the UI)
    Audit view (redacted form, stored in DB)
```

The redaction boundary is a hard gate. No original text crosses it.

---

## Common mental model mistakes

**"Tank knows things I didn't ingest."**
It doesn't. Tank only knows what is in its KB. If you ask about a service that isn't in any ingested doc, Tank will say it doesn't have data on it.

**"Tank stores my secrets so it can answer questions about them."**
Secret tokens are one-way SHA-256 hashed in the redaction map. Tank cannot recover them, by design. You look up actual secret values in your vault, not in Tank.

**"Talking to Tank is like talking to Claude directly."**
Not exactly. Claude has no internet access, no prior knowledge of your company, and no memory between API calls. Tank provides all the context (KB chunks, entity cards, conversation history) in every prompt. Claude reasons over Tank's context, not its own training data.

**"A higher chat setting means more API calls."**
No. Each chat turn is typically one streaming API call (plus tool calls for KB lookups). The cost is driven by the volume of KB context retrieved, not by any "quality setting."
