# MedScribe-R-Us — Company & Scenario Brief

> This is the orientation doc for the **first security hire** at MedScribe-R-Us.
> The scenario is modeled on the public case study at
> https://github.com/LeSpookyHacker/medscribe-r-us-appsec
> (all names, data, and systems are fictional, for demo/testing only).

## The company

MedScribe-R-Us is a Series A healthcare-AI startup (~70 people, ~40 in
engineering). The platform turns patient–clinician conversations into
AI-generated SOAP notes and writes them back to Epic/Cerner over FHIR R4. It
runs entirely on GCP and operates as a HIPAA **Business Associate** for every
customer health system.

- **Crown jewels:** Protected Health Information (PHI) — audio, transcripts,
  clinical notes — and the per-tenant CMEK keys that protect it.
- **Regulatory:** HIPAA/HITECH (primary), SOC 2 Type II (audit window opens
  2026-09-01), HITRUST CSF (year 2), OWASP LLM Top 10, NIST CSF 2.0.
- **Stack:** GCP Cloud Run, MongoDB Atlas, Vertex AI (Gemini), Google
  Speech-to-Text, GCS, Cloud KMS, Secret Manager, Auth0, Datadog.

## Your role (the scenario)

You are **LeSpookyHacker**, **Staff Application Security Engineer** — MedScribe's
**first dedicated security hire**, reporting to the CTO (Aanya Krishnan). Today
is **day one**. Security has so far been a part-time responsibility of the SRE
team; there is no AppSec program, no threat modeling, no CI security gates, no
vulnerability management, and no incident-response playbooks.

Your loose first-90-days mandate:
1. Build a knowledge graph of the platform (this tool).
2. Stand up threat modeling for the AI pipeline + Tier-0 services.
3. Validate the PHI scrubbing layer (the highest-impact control).
4. Get SAST/SCA/secrets/container/DAST gates into CI.
5. Begin SOC 2 / HIPAA evidence collection before the September audit window.

## People you'll meet first

| Name | Role | Why |
|---|---|---|
| Aanya Krishnan | CTO | Your manager; owns the security mandate |
| Dana Okafor | Staff SRE / Platform | Owns GCP, networking, IAM today |
| Priya Raman | Pipeline Eng Lead | Owns ingestion/transcription/EMR-integration |
| Marcus Lee | AI Platform Lead | Owns scrubbing + summarization + validation |
| Tom Bryce | IT / HIPAA Privacy Officer | Owns BAAs, compliance, audit |

## Known top concerns (inherited)

- PHI scrubbing has no validation suite (T-007).
- No prompt-injection testing on the LLM pipeline (T-014).
- Over-broad CI/CD service account in prod (T-013, IAM-2026-014).
- PHI potentially logged by services (T-006).
- Approval-gate enforcement not verified end-to-end (T-009).
