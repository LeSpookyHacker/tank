# DFD Sources (manual upload)

These Mermaid data-flow diagrams are **not** ingested by `load_fixtures.py`.
Upload them into Tank's DFD tool (sidebar → Pipeline → DFD Analysis → Stage 1 →
"Paste Mermaid" or "Upload file") to exercise the STRIDE threat-model workspace.

| File | Service | Pre-analyzed by seed_db? |
|---|---|---|
| `ai-pipeline-dfd.mmd` | AI summarization pipeline | ✅ (cached STRIDE threats) |
| `emr-integration-dfd.mmd` | emr-integration-svc | ✅ (cached STRIDE threats) |
| `clinician-portal-dfd.mmd` | clinician-portal | ❌ (upload to run a fresh analysis) |

The pre-analyzed diagrams load instantly in Stage 3 (⚡ cache badge, no API call).
The clinician-portal diagram is left un-analyzed so you can test a live run.
