# Runbook — investigate a suspicious customer login

**Last reviewed:** 2026-04-22 by Diana Okoro

## Trigger

A Datadog alert from `customer-login-anomaly`. Common reasons:

- New device + new geo for the same end-user in <1 hour.
- A spike in failed logins followed by a successful one.
- A successful login from a Tor exit node or known-abusive IP.
- Multiple successful logins for the same `sub` within 5 minutes
  from different geos.

The alert pages the security-watch rotation (currently Diana; you
once you start).

## Investigate

1. Get the customer_id + sub from the alert payload.

2. Pull recent auth events for that sub:

   ```bash
   # Datadog Logs query
   service:identity-svc @event.kind:auth.* @claims.sub:<sub> @claims.customer_id:<customer_id>
   ```

   Look at the last ~30 days.

3. Cross-check against the customer's SSO IdP if they federate.
   Most do; check the OEM-side audit log.

4. Look at downstream activity:

   ```bash
   service:payments-api @auth.sub:<sub>
   service:orders-api @auth.sub:<sub>
   ```

   Any charges or order changes after the suspicious login?

## Decide

- **Confirmed compromise** (likely): trigger
  `policies/incident-response.md`, declare Sev-2 minimum. Force-
  revoke the user's session (admin console).
- **Likely false positive** (legit travel, family using same login):
  document in the alert's "investigated" notes. No further action.
- **Inconclusive**: lower-risk path — soft-revoke the session and
  notify the customer's admin contact via the integration owner.
  Ask them to confirm with the end-user.

## Force-revoke session

```bash
curl -X POST \
  -H "Authorization: Bearer $VAULT_ISSUED_TOKEN" \
  https://identity.helix.internal/admin/sessions/<session_id>/revoke
```

This invalidates the access_token and any associated refresh tokens.
The end-user will be forced to re-authenticate.

## Notify

For confirmed compromises, the comms responsibility is on the
customer-success owner for that account, not you. Hand off via
`#customer-incidents` Slack.

## Patterns to escalate

- 3+ suspicious-login incidents per week from the same customer →
  raise to that customer's CSM; their integration may be allowing
  credential reuse.
- Repeat sub across multiple alerts → look for a slow credential
  stuffing campaign. Diana has dashboards.
