# webhook-router

Internal event bus → outbound HTTPS POSTs to customer-supplied webhook
URLs. HMAC-signed. Retries with exponential backoff up to 24 hours.

**Owner:** Yui Tanaka (yui@helix.internal)
**Team:** Platform
**On-call rotation:** Platform on-call (PagerDuty service
`platform-prod`)
**Tier:** 1 (customer-impacting if down, but not customer-visible
synchronously)
**Repo:** `github.com/helix-robotics/webhook-router`

## What it does

1. Tails a Kinesis stream `helix-prod-events` for internal events.
2. Loads customer webhook configs from DynamoDB
   `helix-webhook-configs`.
3. For each matching subscription, builds an HMAC-SHA256 signature
   over the payload + timestamp, sends `POST` to the customer's URL.
4. Persists delivery attempts to DynamoDB `helix-webhook-events`;
   retries failed deliveries with exponential backoff up to 24h.

## Production

- ECR image:
  `999988887777.dkr.ecr.us-west-2.amazonaws.com/webhook-router`
- EKS namespace: `platform-prod`, 4 replicas
- DNS: not customer-facing; metrics-only resolution at
  `webhooks.helix.internal`
- DynamoDB tables (account `999988887777`):
  `helix-webhook-configs`, `helix-webhook-events`
- Kinesis stream: `helix-prod-events` (shared with other consumers)
- Egress NAT: `10.50.250.0/24` (publish to customers for allowlists)

## Signing

HMAC-SHA256 over `${timestamp}.${body}` with a per-customer secret
held in Vault at `secret/webhook-router/prod/customer-secrets/<id>`.

Header layout (matches Stripe's signature spec):

```
Helix-Signature: t=<unix_timestamp>,v1=<hex_hmac>
```

Customers verify timestamp freshness (we recommend 5 minutes) and
recompute the HMAC over the same string.

## Open items

(Yui's notes; would be worth threat-modeling.)

- **SSRF surface** — we POST to customer-supplied URLs. We restrict
  to `https://` but don't deny private/link-local IP ranges
  (`10/8`, `169.254/16`, `127.0.0.1`, etc.). A malicious customer
  could register a webhook URL that resolves to `pii.helix.internal`
  or `vault.helix.internal`. Tracked in HELIX-1822.
- No postmortem on file — webhook-router has historically just not
  broken.
- No runbook on file. If it pages at 3am, the on-call engineer is
  reading the source.
- Backpressure is naive: if Kinesis lag grows, we just consume more
  slowly. No customer-facing telemetry yet.
