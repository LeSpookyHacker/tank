# AI Pipeline DFD (L2) — MedScribe-R-Us

> Owner: AppSec · Status: Draft v1.0
> Data-flow diagram for the de-identification → summarization → validation path.
> Addresses T-007 (scrubbing gap), T-008 (token-map leak), T-014 (indirect prompt injection).

The most security-sensitive flow in the platform: the only place de-identified
PHI leaves MedScribe's control (to Vertex AI), and where LLM output re-enters
the clinical record.

```mermaid
flowchart TD
    C[Clinician] -->|TLS 1.3| GW[API Gateway]
    GW --> TR[Transcription Service]
    TR -->|raw transcript| DB[(MongoDB: transcripts)]
    DB --> PS[PHI Scrubbing Layer]
    PS -->|token map| TM[(MongoDB: token_maps)]
    PS -->|de-identified text| AISUM[AI Summarization Engine]
    AISUM -->|de-id transcript + prompt| VAI[[Vertex AI Gemini]]
    VAI -->|untrusted output| OV[Output Validation]
    OV -->|re-inject from token map| TM
    OV --> NOTES[(MongoDB: notes draft)]
    NOTES --> CP[Clinician Portal review/approve]
    CP --> EMR[EMR Integration]
    EMR -->|FHIR R4 SMART| EPIC[[Epic / Cerner]]
    PRIOR[Prior EMR notes] -.indirect prompt injection T-014.-> AISUM
```

## Trust boundaries
- **B1** Internet → API Gateway (Cloud Armor WAF).
- **B2** MedScribe VPC → Vertex AI (VPC Service Controls perimeter). Only
  de-identified text crosses.
- **B3** MedScribe VPC → Epic/Cerner (SMART on FHIR OAuth, encounter-scoped).

## Key threats on this flow
- **T-007** Scrubbing false-negative → real PHI reaches Vertex AI. Defense:
  layered NER + regex; labeled-corpus validation suite; output PHI-pattern scan.
- **T-008** Wrong token map on re-injection → Patient A's PHI in Patient B's
  note. Defense: HMAC session binding validated before any substitution.
- **T-014** Prior EMR note carries an injection payload into LLM context.
  Defense: delimit prior notes as untrusted data; instruction-pattern anomaly
  detection on output; sanitize prompt-control characters.
