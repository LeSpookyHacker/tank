# Runbook — restart a prod service

**Last reviewed:** 2026-03-04 by Alice Tanaka
**Applies to:** any service in EKS namespace `*-prod`

## When to use

- A service is unhealthy (pods crash-looping, p99 latency spiking)
  and a restart is a safe first step.
- Following a config-only change that requires a rolling restart.

When **not** to use:

- During an active security incident — see
  `policies/incident-response.md` first. Restarting may destroy
  forensic state.
- During an active customer-impacting outage when you don't know the
  cause — escalate to the platform on-call first.

## Prerequisites

- AWS Identity Center session in role `PlatformEngineer` (or higher).
- kubectl configured for the prod EKS cluster
  (`helix-prod-us-west-2`).
- A buddy in `#platform-eng` — never restart prod alone.

## Procedure

```bash
# 1. Confirm cluster + namespace
kubectl config current-context
# expected: arn:aws:eks:us-west-2:999988887777:cluster/helix-prod-us-west-2
kubectl get deploy -n <namespace>

# 2. Note the current generation + image
kubectl get deploy <service> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# 3. Rolling restart
kubectl rollout restart deploy/<service> -n <namespace>

# 4. Watch the rollout
kubectl rollout status deploy/<service> -n <namespace>

# 5. Smoke test
curl -sf https://<service>.helix.internal/healthz | jq .

# 6. Verify Datadog metrics aren't worsening
# Dashboard: https://helix.datadoghq.com/dashboard/<service>-overview
```

## If the rollout fails

```bash
kubectl rollout undo deploy/<service> -n <namespace>
```

## Post-restart

- Confirm the restart in `#platform-eng` (one-line: "restarted X
  for reason Y, normal status now").
- If this restart was triggered by an alert, snooze or close the
  alert.

## Service-specific notes

- **identity-svc**: token issuance halts briefly during rollout.
  Restart in off-peak hours (between 02:00–06:00 UTC ideal) unless
  emergency.
- **payments-api**: in-flight charges complete (we don't kill TCP
  mid-flight); rollout takes ~90s with 6 replicas. Stripe will
  retry on its side if any requests are interrupted.
- **webhook-router**: see `runbooks/webhook-router-recovery.md`.
  TODO: this runbook does not exist yet. If you need it, ping Yui.
