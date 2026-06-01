# Network Security — MedScribe-R-Us (GCP)

> Owner: AppSec · Status: Draft v1.0
> Addresses T-002 (API Gateway bypass), T-012 (audio DoS), T-013 (Secret Manager).

## VPC topology

- One Shared VPC per environment. Prod project: `medscribe-prod`.
- All Cloud Run services deployed with ingress `internal-and-cloud-load-balancing`.
- The **only** public ingress is the external HTTPS Load Balancer →
  `api.medscribe.internal` (API Gateway), fronted by Cloud Armor WAF.
- Egress to Google APIs (Vertex AI, STT, KMS, Secret Manager) restricted by a
  **VPC Service Controls** perimeter — exfiltration outside the perimeter is denied.

## Subnets & ranges (illustrative)

| Subnet | CIDR | Purpose |
|---|---|---|
| svc-frontend | 10.20.0.0/22 | API Gateway, portals |
| svc-pipeline | 10.20.4.0/22 | ingestion/transcription/scrub/summary/validation |
| svc-data | 10.20.8.0/22 | MongoDB private endpoint, KMS access |
| mgmt | 10.20.30.0/24 | break-glass bastion (`10.20.30.40`), ops tooling |

## Controls

- **Cloud Armor**: rate limiting per tenant; OWASP CRS; geo rules; bot defense.
- **Firewall**: deny-all default; only the LB SA may reach API Gateway; only the
  Gateway SA may reach pipeline services; pipeline → data is single-direction.
- **Private Service Connect** to MongoDB Atlas; Atlas IP allowlist limited to the
  PSC endpoint at `mongo-prod.medscribe.internal`.
- **mTLS** between all internal services (SPIFFE IDs via Workload Identity).
- **TLS 1.3** on all external endpoints; HSTS; modern cipher suite only.

## T-002 — API Gateway bypass

Cloud Run ingress misconfiguration (a known GCP footgun) could expose an internal
service directly. Mitigation: enforce `internal-and-cloud-load-balancing` ingress
on every service via Terraform policy + a CI check that fails the build if any
service is set to `all`. Quarterly ingress configuration audit.

## T-012 — Audio DoS

API Gateway enforces max audio duration (4 h) and file-size caps; streaming
sessions time out on inactivity; Cloud Run concurrency + memory caps; per-tenant
GCS quotas to bound Speech-to-Text spend.

## Open items

- Egress proxy for the AI Summarization Engine not yet pinned to Vertex-only.
- Cloud Armor custom rules for the FHIR callback path are still permissive.
