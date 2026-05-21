# Internal hosts + IPs — bare list

> **Why this file exists**: tests Tank's hostname and IP redaction
> rules. Every line below should result in placeholder substitutions.
> The same hostname appearing multiple times across other fixture
> files should map to the same placeholder, demonstrating Tank's
> deterministic redaction-map keying.

## Internal hostnames (should redact)

- `vault.helix.internal`
- `auth.helix.internal`
- `identity.helix.internal`
- `payments.helix.internal`
- `orders.helix.internal`
- `webhooks.helix.internal`
- `devices.helix.internal`
- `pii.helix.internal`
- `ca.helix.internal`
- `internal-admin.helix.internal`
- `hr-portal.corp` (matches the default `*.corp` rule)
- `wiki.corp`
- `vpn.corp`

## Private IPs (should redact)

- `10.50.10.5`
- `10.50.20.18`
- `10.50.250.1`  (NAT egress)
- `10.51.10.5`
- `192.168.1.1` (someone's local laptop, somehow in a log line)
- `127.0.0.1` (loopback)
- `169.254.169.254` (instance metadata service — sensitive)
- `100.64.0.1` (CGNAT)

## Public hostnames (should NOT redact by default)

- `auth.helix.io`
- `payments.helix.io`
- `app.helix.io`
- `api.stripe.com`
- `docs.python.org`

## Public IPs (should NOT redact by default)

- `52.27.45.10`
- `52.27.45.11`
- `52.27.45.12`
  (these are the publicly-allowlisted webhook-router NAT egress IPs)

## Verification

After ingesting this file via Tank:

```sql
-- Should see at least 13 unique placeholders in this category
SELECT count(*) FROM redaction_map WHERE category = 'internal_hostname';

-- Should see at least 8 unique placeholders here
SELECT count(*) FROM redaction_map WHERE category = 'ipv4_private';

-- Should see ZERO entries (public, off by default)
SELECT count(*) FROM redaction_map WHERE category = 'public_hostname';
SELECT count(*) FROM redaction_map WHERE category = 'ipv4_public';

-- Same hostname appearing in multiple docs should still show
-- occurrence_count > 1 for the original placeholder
SELECT placeholder, occurrence_count
  FROM redaction_map
  WHERE category = 'internal_hostname'
  ORDER BY occurrence_count DESC
  LIMIT 5;
```
