# Runbook — LLM Prompt-Injection Incident

> Owner: AppSec + AI Platform · Relates to T-014 (indirect prompt injection)

## When to use
The Output Validation Service flags instruction-like patterns in Vertex AI
output, or a generated SOAP note contains content not supported by the
transcript (possible injection via prior EMR notes).

## Steps

1. **Quarantine the note.** Mark the affected `notes` document `status=quarantine`
   so it cannot be approved or written to the EMR.
2. **Capture context.** Save the de-identified prompt, the LLM response, and the
   `session_id`. Do NOT pull raw PHI into the ticket.
3. **Find the source.** Identify whether the payload entered via prior EMR notes
   (T-014) or a scrubbing gap (T-007). Check which tenant/encounter.
4. **Contain.** If a specific prior-note source is implicated, disable prior-note
   context for that tenant until reviewed.
5. **Notify clinician.** The assigned clinician must be told the draft is
   withheld pending review (no auto-approval).
6. **Eradicate.** Strengthen prompt delimiting / output anomaly rules; add the
   payload to the prompt-injection test corpus.
7. **Review.** Postmortem if any unapproved content reached a clinician or EMR.
