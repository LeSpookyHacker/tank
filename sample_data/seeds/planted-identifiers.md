# Planted Internal Identifiers (redaction test fixtures)

> Internal hostnames, an internal IP, and the corporate email domain. All must be
> redacted (`[INTERNAL_HOST_xxx]`, `[PRIVATE_IP_xxx]`, `[EMAIL_xxx]`) before any
> text reaches Claude. Used by `scripts/verify_privacy.py --fixture-pack`.

## Internal hostnames

- API Gateway: `api.medscribe.internal`
- MongoDB Atlas PSC endpoint: `mongo-prod.medscribe.internal`
- Vertex AI egress proxy: `vertex-proxy.medscribe.internal`
- Auth/OIDC issuer: `auth.medscribe.internal`

## Internal network

- Break-glass bastion: `10.20.30.40` (mgmt subnet)

## Corporate email domain

- Engineering distro: `engineering@medscribe-r-us.fake`
- Security alias: `security@medscribe-r-us.fake`

## Why this file exists

Tank's headline guarantee is that nothing reaches the Anthropic API in cleartext.
This fixture plants known-bad identifiers so the privacy assertion can confirm the
redaction chokepoint (`app/redact/engine.py`) actually fired on every category.
