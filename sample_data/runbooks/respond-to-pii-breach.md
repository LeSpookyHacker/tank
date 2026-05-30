# Runbook: Respond to PII Breach or Suspected PII Exposure

**Runbook ID**: RB-SEC-004  
**Owner**: Unowned — interim-held by Tom Brandt (CTO); transfers to the incoming first security hire within first 30 days  
**Last updated**: 2026-03-01  
**Applies to**: Any suspected or confirmed unauthorized access to customer PII
stored in `pii-vault` or replicated to the analytics pipeline.

---

## When to invoke this runbook

Invoke immediately if any of the following are observed:

- Unauthorized access to `pii-prod-pg` RDS instance detected in CloudTrail/Datadog.
- Break-glass Vault access outside a declared incident window.
- Bulk export of customer billing addresses not attributable to a known job.
- S3 pre-signed URL for PII data shared externally (detected in CloudTrail).
- `pii-vault` process crash with heap dump written to disk.
- Any employee or contractor reports suspected access to customer PII.

---

## Severity classification

| Signal | Severity |
| --- | --- |
| Confirmed exfiltration of PII records | P0 — immediate all-hands |
| Unauthorized DB access, no confirmed read | P1 — within 15 minutes |
| Suspected but unconfirmed access | P2 — within 1 hour |

---

## Step 1: Alert and assemble

**IC (Incident Commander)**: SRE on-call lead (alice.tanaka@helixrobotics.com)
today — there is no security on-call yet. Once the incoming first security hire
joins, this role transfers to them.

Page the following via PagerDuty immediately:

- `platform-on-call` (alice.tanaka@helixrobotics.com primary)
- Security on-call
- CTO: tom.brandt@helixrobotics.com (P0/P1 only)

Open a Slack channel `#inc-YYYYMMDD-pii` and post the initial incident report
template (link: [Jira template HELIX-INC-001]).

---

## Step 2: Containment (first 15 minutes)

### 2a. Isolate pii-vault

```bash
# Scale down pii-vault to zero replicas (stops new requests)
kubectl scale deployment pii-vault --replicas=0 -n production

# Verify no traffic is reaching pii-vault
kubectl get pods -n production -l app=pii-vault
```

### 2b. Revoke the mTLS client certificate (payments-api → pii-vault)

```bash
# Revoke via Vault PKI
vault write pki/revoke serial_number=<payments-api-cert-serial>

# Force payments-api to re-request a new cert on next Vault Agent refresh
kubectl rollout restart deployment/payments-api -n production
```

### 2c. Rotate the Vault bearer token for pii-vault

```bash
# Revoke all tokens issued to pii-vault approle
vault token revoke -mode=path auth/approle/pii-vault/

# New tokens will be issued on next deployment
```

### 2d. Rotate the CMK (if key is suspected compromised)

**Warning**: Rotating a KMS CMK does NOT re-encrypt existing data. It changes
the key used for new encryption operations. Contact AWS support if a CMK is
confirmed compromised — deletion requires a 7-30 day pending window.

```bash
# Schedule key rotation (takes effect within 24 hours)
aws kms enable-key-rotation --key-id alias/helix-pii-prod
```

---

## Step 3: Assess scope

### 3a. Pull Vault audit logs

```bash
# Vault audit logs in Datadog
# Query: source:vault path:pii-vault @event.type:request
# Time window: last 24 hours (or widen as needed)
```

### 3b. Pull RDS audit logs (CloudTrail)

```bash
# CloudTrail RDS data events for pii-prod-pg
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=pii-prod-pg \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)
```

### 3c. Count potentially affected records

```sql
-- Connect via break-glass Vault token (requires two-person approval)
SELECT COUNT(*) FROM pii.customer_pii
WHERE updated_at >= '<incident-start-timestamp>';
```

Record the count and the time range in the incident channel. This is needed
for GDPR notification.

---

## Step 4: Notification timelines

### GDPR (EU customers)

- **72 hours** from discovery: notify the relevant Data Protection Authority
  (Ireland DPC for EU customers, per GDPR Article 33).
- **Without undue delay**: notify affected customers if the breach is likely
  to result in a high risk to their rights and freedoms (GDPR Article 34).

Contact: legal@helixrobotics.com. Do not wait for full scope assessment before
alerting legal.

### OEM customer contracts

- **24 hours** from confirmed breach: direct notification to affected OEM
  customers per standard Helix contract clause 12.4 (Data Security Incident).
- Notification drafted by Legal; reviewed by CTO.
- Template: legal@helixrobotics.com → "PII Breach OEM Notification Template".

### AWS

If the breach involved a compromised AWS credential or CMK:
- File an AWS Security Hub finding.
- If criminal activity is suspected, file an AWS abuse report.

---

## Step 5: Remediation and recovery

1. Deploy `pii-vault` with new mTLS cert, new Vault token, and verified
   container image (confirm digest against build registry).
2. Restore `payments-api` to point to the new pii-vault endpoint.
3. Verify end-to-end: `GET /pii/<test-customer-id>` returns expected data.
4. Scale back to normal replica count.
5. Enable enhanced CloudTrail logging for `pii-prod-pg` for 30 days post-incident.

---

## Step 6: Post-incident

- Within 5 business days: write postmortem (template: [Jira HELIX-INC-002]).
- Within 10 business days: present findings to CTO and Legal.
- Actions items tracked in Jira with owners and due dates.
- Lessons extracted to Tank's lessons DB.

---

## Contacts

| Role | Contact |
| --- | --- |
| Security on-call | none yet — SRE on-call covers (alice.tanaka@helixrobotics.com) until the first security hire |
| Platform on-call | alice.tanaka@helixrobotics.com |
| CTO (P0/P1) | tom.brandt@helixrobotics.com |
| Legal | legal@helixrobotics.com |
| AWS TAM | via AWS Support Console (Priority Support) |
