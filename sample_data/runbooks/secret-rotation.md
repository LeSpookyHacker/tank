# Runbook — Secret Rotation / Compromise

> Owner: AppSec + Platform · Relates to T-013 (Secret Manager compromise)

## Secrets in scope
Vertex AI API key, MongoDB Atlas connection string, FHIR OAuth client secret,
Datadog API key, Auth0 client secret. All live in GCP Secret Manager
(`secrets-prod`).

## Routine rotation
- API keys: 90 days. OAuth secrets: 180 days. Driven by Secret Manager rotation.

## On suspected compromise

1. **Rotate immediately** in Secret Manager (create a new version, disable the old).
2. **Redeploy** the consuming Cloud Run service so Workload Identity picks up the
   new version; verify via `secret_version_accessed` in audit logs.
3. **Revoke at the source** — disable the leaked Vertex/Datadog/Auth0 credential
   in the provider console; for MongoDB, rotate the DB user password.
4. **Hunt.** Search `audit_events` + Cloud Logging for use of the old secret after
   the suspected leak time.
5. **Check blast radius.** If the leaked SA had broad scope (e.g. ci-deploy,
   IAM-2026-014), treat as potential full PHI compromise → PHI breach runbook.
6. **Record** a decision/lesson and update the rotation schedule if needed.

## Do not
Never paste a secret value into a ticket, chat, or log. Reference the secret by
its Secret Manager resource name only.
