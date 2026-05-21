# Runbook — rotate a customer API key

**Last reviewed:** 2026-04-09 by Marcus Chen
**Applies to:** OAuth client secrets issued to OEM customers
(stored in identity-svc Postgres, encrypted via Vault transit
engine).

## When to use

- Customer reports their client secret was exposed (committed to a
  public repo, included in a screenshot, etc.)
- Routine rotation per customer schedule (we offer annual rotation;
  most customers haven't taken us up on it).
- Suspected compromise (paired with `policies/incident-response.md`).

## Prerequisites

- Access to identity-svc admin console (SSO + role `Security` or
  `PlatformEngineer`).
- Vault token with `identity-svc` policy attached.
- Direct line to a customer contact who can update their integration
  within the cutover window.

## Procedure

1. **Open admin console**:
   `https://identity-admin.helix.internal/customers/<customer_id>`

2. **Generate new secret**:

   ```bash
   curl -X POST \
     -H "Authorization: Bearer $VAULT_ISSUED_TOKEN" \
     https://identity.helix.internal/admin/customers/<customer_id>/rotate-secret
   ```

   Response includes the new secret in plaintext — copy it once,
   never again. Use 1Password to share with the customer.

3. **Both secrets are valid during a 24-hour overlap window.** This
   is intentional: the customer rotates on their side without
   downtime.

4. **Confirm customer cutover.** Customer pings back "we're using
   the new secret in prod."

5. **Revoke old secret** before the 24-hour window ends:

   ```bash
   curl -X DELETE \
     -H "Authorization: Bearer $VAULT_ISSUED_TOKEN" \
     https://identity.helix.internal/admin/customers/<customer_id>/secrets/<old_kid>
   ```

6. **Verify** by attempting to use the old secret — should 401.

7. **Document** the rotation in the customer's contact record
   (Salesforce). For incident-driven rotations, also file a
   postmortem.

## What can go wrong

- Customer takes longer than 24 hours → extend the overlap window.
  Document in HELIX-OPS Jira.
- Customer needs the old secret back → impossible, never stored
  in plaintext. Generate another new secret + extend the new-new
  overlap window.
- The rotate endpoint 500s → check Vault status; the transit
  engine must be unsealed for the rotation to succeed.

## Related

- Internal rotation (Stripe restricted keys, internal CA, JWT
  signing keys) follows the same overlap-window pattern. Marcus
  owns each of those runbooks individually.
- See `policies/data-classification.md` — client secrets are
  Restricted tier.
