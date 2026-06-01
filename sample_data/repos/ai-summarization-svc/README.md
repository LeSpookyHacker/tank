# ai-summarization-svc

MedScribe-R-Us **AI Summarization Engine** (Tier-0, PHI). Cloud Run service that
takes a **de-identified** transcript, builds a structured prompt, calls Vertex AI
(Gemini), and returns a SOAP note draft for the Output Validation Service.

> ⚠️ Synthetic sample repo for Tank demos. Contains deliberately weak patterns
> (PHI logging, an over-trusting scrubber, prompt construction without output
> validation) used to demonstrate code-aware security review. Do not deploy.

## Architecture
- `main.py` — FastAPI app, `POST /summarize`.
- `phi_scrub.py` — NER/regex de-identification (has known gaps — see T-007).
- `vertex_client.py` — Vertex AI Gemini wrapper.
- `config.py` — config + secrets (GCP Secret Manager via Workload Identity).

## Security notes (open)
- T-006: exception handler logs request body (PHI risk).
- T-007: scrubber misses informal name/date formats.
- T-014: prior-note context is concatenated into the prompt without delimiting.

## Run
```
uvicorn ai_summarization_svc.main:app --port 8080
```
Reads `VERTEX_PROJECT`, `VERTEX_LOCATION`, and pulls the Vertex key from
Secret Manager (`projects/medscribe-prod/secrets/vertex-api-key`).
