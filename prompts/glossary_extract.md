# Glossary candidate extraction

You are scanning recent KB chunks for **company-specific jargon** —
multi-word terms, acronyms, internal project nicknames, or shorthand
that a new hire wouldn't recognize.

## Your job

Produce a `GlossaryExtraction` of glossary `candidates`:

1. **term** — the term as written (preserve case for proper nouns).
2. **definition** — 1-sentence plain-English definition inferred from
   how it's used in the chunks. If the chunks don't make the
   definition clear, set definition to "(unknown — needs human
   input)" and let the user fill it in.
3. **aliases** — other ways the same thing is referenced. Optional.

## Rules

- **Only company-specific jargon.** Skip standard English ("the",
  "service"), standard infosec vocabulary (TLS, MFA, OAuth), and
  standard cloud terms (S3, IAM, Lambda).
- **Multi-word over single-word.** Single-word jargon is rare;
  prefer phrases like "Vault sidecar", "tier-2 service", "OEM tier".
- **Acronyms welcome if they're internal.** "SLA" no. "PCG" (a
  made-up internal team) yes.
- **Quality > quantity.** 5 confident candidates beat 20 noisy ones.

## Output

Return a `GlossaryExtraction`. If the chunks contain no clear
candidates, return `candidates: []`.
