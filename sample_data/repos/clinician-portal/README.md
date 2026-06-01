# clinician-portal

MedScribe-R-Us **Clinician Portal** (Tier-0, PHI). Next.js 15 app where clinicians
review, edit, and **approve** AI-generated SOAP notes before EMR write-back.

> ⚠️ Synthetic sample repo for Tank demos. Contains deliberately weak patterns
> (client-trusted approval flag, tenant_id from a header) to demonstrate
> code-aware security review. Do not deploy.

## Routes
- `pages/index.tsx` — note review queue.
- `pages/api/notes/[id]/approve.ts` — approval endpoint (see T-009 note).
- `lib/auth.ts` — JWT verification + tenant resolution (see T-011 note).

## Security notes (open)
- T-009: approval state is sent from the client; the server should re-read note
  state from MongoDB and never trust the request body.
- T-011: `tenant_id` is read from the `x-tenant-id` header instead of the verified
  JWT claim — horizontal privilege-escalation risk.

## Run
```
npm install && npm run dev
```
