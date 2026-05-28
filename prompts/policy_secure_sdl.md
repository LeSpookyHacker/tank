Generate a first-draft Secure Development Lifecycle (SDL) Policy using the company context in the KB scope.

Follow the base policy rules. Additional specifics for SDL:
- Cover: threat modeling requirements (when and how), code review security checklist, dependency scanning, secrets management, pre-production security review, penetration testing cadence.
- Tailor to the company's primary stack if known (e.g., specific to Python, Node.js, Go, etc.).
- If the company has a CI/CD platform, reference it specifically.
- Set achievable requirements — this is a starting SDL for a company with no existing security process, not a mature SDLC.
- Design review: specify when a design review is required (e.g., "any feature that processes PII or handles authentication").

Return only the policy text in Markdown format. No preamble, no explanation.
