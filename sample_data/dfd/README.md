# DFD Source Files — For Manual Upload into Tank's DFD Tool

These `.mmd` files are **Mermaid source diagrams** for Helix Robotics services.
They are **not** ingested by `load_fixtures.py` — they are input files for
Tank's DFD Threat Modeling tool.

## How to use

1. Open Tank → **Pipeline → DFD Analysis** (or click the DFD link in the sidebar).
2. Select **Tab B: Upload File**.
3. Drag-and-drop any `.mmd` file from this directory, or click to browse.
4. Tank loads the Mermaid source into the editor (Tab A) for review.
5. Click **Run Threat Analysis** to run STRIDE.

Alternatively, use **Tab A: Paste Mermaid** and copy-paste the file contents.

## Files

| File | Service | Expected threats |
| --- | --- | --- |
| `payments-api-dfd.mmd` | payments-api → pii-vault → RDS → Stripe | ~12 threats (JWT bypass, mTLS cert compromise, SQL injection, Stripe key exposure, Redis hijack) |
| `identity-svc-dfd.mmd` | identity-svc → RDS → Redis → Vault → Okta | ~10 threats (OIDC replay, RDS password auth, JWKS cache staleness, Redis unauthenticated) |
| `pii-vault-dfd.mmd` | pii-vault isolated service | ~8 threats (mTLS compromise, bulk export, break-glass undetected, CMK deletion) |
| `webhook-router-dfd.mmd` | webhook-router → DynamoDB → Customer URLs | ~8 threats (SSRF, credential exfiltration via IMDS, DynamoDB injection) |

## Pre-seeded results

`scripts/seed_db.py` pre-loads analyzed results for `payments-api-dfd.mmd` and
`identity-svc-dfd.mmd` into the database. You can view them immediately at
`GET /dfd` without making an API call:

- payments-api analysis: `GET /dfd/<id>` (see seed_db.py output for the ID)
- identity-svc analysis: `GET /dfd/<id>`

The cache badge (⚡ Loaded from cache) will show on both.
