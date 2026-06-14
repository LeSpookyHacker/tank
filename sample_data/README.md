# Sample Data — MedScribe-R-Us

Everything in this directory is **fictional**. Names, systems, hostnames, keys, PHI, and
org details are invented for demonstration and testing purposes only. The scenario is
modeled on the public case study at
[LeSpookyHacker/medscribe-r-us-appsec](https://github.com/LeSpookyHacker/medscribe-r-us-appsec).

---

## The scenario

**MedScribe-R-Us** is a Series A healthcare-AI startup (~70 people, ~40 in engineering).
The platform converts patient–clinician conversations into AI-generated SOAP notes and
writes them back to Epic/Cerner over FHIR R4. It runs entirely on GCP and operates as a
HIPAA Business Associate for every customer health system.

**You are LeSpookyHacker** — Staff AppSec Engineer, MedScribe's **first dedicated security
hire**, reporting to CTO Aanya Krishnan. Today is day one. There is no AppSec program,
no threat modeling, no CI gates, no vulnerability management, and no IR playbooks. That's
why they hired you.

**Key people you'll meet:**

| Name | Role |
|---|---|
| Aanya Krishnan | CTO — your manager, owns the security mandate |
| Dana Okafor | Staff SRE / Platform — owns GCP, networking, IAM |
| Priya Raman | Pipeline Eng Lead — owns ingestion, transcription, EMR integration |
| Marcus Lee | AI Platform Lead — owns scrubbing, summarization, validation |
| Tom Bryce | IT / HIPAA Privacy Officer — owns BAAs, compliance, audit |

**Your first-90-days mandate:**
1. Build a knowledge graph of the platform.
2. Stand up threat modeling for the AI pipeline and Tier-0 services.
3. Validate the PHI scrubbing layer (the highest-impact control).
4. Get SAST / SCA / secrets / container / DAST gates into CI.
5. Begin SOC 2 / HIPAA evidence collection before the September audit window.

**Inherited concerns you'll find in the data:**
- PHI scrubbing has no validation suite (T-007)
- No prompt-injection testing on the LLM pipeline (T-014)
- Over-broad CI/CD service account in prod (T-013, IAM-2026-014)
- PHI potentially logged by services (T-006)
- Approval-gate enforcement not verified end-to-end (T-009)

---

## Directory inventory

| Directory / File | Contents | Tank ingest type |
|---|---|---|
| `company.md` | Scenario brief, company background, your role, key contacts, inherited concerns | `architecture` |
| `architecture/` | System overview, PHI data-flow, IAM design, network security, AI pipeline DFD (MD + PNG) | `architecture` |
| `cmdb/` | GCP resource inventory (CSV), services registry (CSV) | `cmdb` |
| `compliance/` | HIPAA, NIST CSF 2.0, and SOC 2 control frameworks (JSON) | `control_framework` |
| `detections/` | 5 Sigma rules (anomalous clinician login, approval-gate bypass, PHI bulk access, Secret Manager access, Vertex PHI-in-output) + Semgrep custom rules | `sigma` / `architecture` |
| `dfd/` | 3 Mermaid DFDs — AI pipeline, clinician portal, EMR integration — see `dfd/README.md` | manual upload to DFD tool |
| `iam/` | GCP IAM bindings (JSON), overbroad role definition (JSON) | `iam` |
| `people/` | Org chart (MD), team directory (CSV), on-call roster (CSV) | `people` |
| `policies/` | Data classification (MD + DOCX), regulatory context, security gates policy, vuln SLA policy | `policy` |
| `postmortems/` | 3 incident write-ups: STT cost spike (2026-03), approval-gate pentest finding (2026-04), PHI-in-logs near miss (2026-05) | `architecture` |
| `repos/` | 2 source repos: `clinician-portal` (Next.js) and `ai-summarization-svc` (Python/FastAPI) | `repo` |
| `runbooks/` | 4 IR runbooks: cross-tenant access, PHI breach response, prompt-injection incident, secret rotation | `architecture` |
| `seeds/` | `planted-identifiers.md` (known-bad hostnames/IPs/emails for redaction testing), `leaked-key-example.md` | internal — used by verify_privacy |

> **DFD note:** The files in `dfd/` are not ingested by `load_fixtures.py`. Upload them
> manually through the DFD tool (sidebar → DFD Analysis → Stage 1 → "Paste Mermaid" or
> "Upload file"). `ai-pipeline-dfd.mmd` and `emr-integration-dfd.mmd` are pre-analyzed by
> `seed_db` and will load from cache instantly. `clinician-portal-dfd.mmd` is left fresh
> so you can run a live STRIDE analysis.

---

## How to load it

Run these four commands in order. Each is idempotent.

```bash
# 1. Render PDF / DOCX / PNG from the Markdown sources
python -m scripts._gen_fixtures

# 2. Ingest all documents + both source repos (uses your ANTHROPIC_API_KEY)
python -m scripts.load_fixtures

# 3. Seed living artifacts — risks, vulnerabilities, threat models, 90-day plan
python -m scripts.seed_db

# 4. Assert the privacy contract held — exit 0 = pass, exit 1 = leak detected
python -m scripts.verify_privacy --fixture-pack
```

`load_fixtures` makes real Claude API calls for entity extraction. Budget ~$0.10–0.30 for
a full run depending on cache state. `seed_db` calls Sonnet to generate threat models, risk
assessments, and the 90-day plan — budget another ~$0.20–0.50.

---

## What you'll see in Tank after loading

- **Knowledge graph** — entities for all 14 types: services (api-gateway,
  ai-summarization-svc, clinician-portal, emr-integration-svc, …), people (Aanya,
  Dana, Priya, Marcus, Tom, and the rest of the org chart), teams, controls, detections,
  IAM policies, runbooks, and more.
- **Chat** — ask questions like "What talks to the PHI database?", "Who owns the
  AI summarization service?", "What are the open risks?", "Which Sigma rules cover
  credential access?".
- **Threat models** — pre-seeded for the AI pipeline and EMR integration services, with
  T-006 through T-014 already captured and linked to the knowledge graph.
- **Risk register** — open risks with likelihood × impact scores, inherited from the
  threat models and postmortems.
- **Vulnerabilities** — intake queue pre-populated from the postmortem findings.
- **90-day plan** — week-by-week task list generated from the scenario's mandate.
- **Reports** — run any of the 14 report kinds; the KB is dense enough to produce
  meaningful output immediately.

---

## Privacy assertion

`seeds/planted-identifiers.md` documents the known-bad identifiers deliberately embedded
throughout the fixture data:

- **Internal hostnames:** `api.medscribe.internal`, `mongo-prod.medscribe.internal`,
  `vertex-proxy.medscribe.internal`, `auth.medscribe.internal`
- **Internal IP:** `10.20.30.40` (break-glass bastion)
- **Email domain:** `@medscribe-r-us.fake`

`scripts/verify_privacy --fixture-pack` scans every redacted-text column in the database
for these strings after ingest. Exit 0 means the redaction chokepoint
(`app/redact/engine.py`) fired correctly on every category and nothing reached the
Anthropic API in cleartext. **Run it after every ingest.**
