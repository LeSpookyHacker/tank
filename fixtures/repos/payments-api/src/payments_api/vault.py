"""Vault client bootstrap.

Uses the Kubernetes auth method via the projected service-account token.
In local dev, falls back to VAULT_TOKEN from env.
"""
from __future__ import annotations

import os
from pathlib import Path

import hvac
import structlog

from payments_api.config import Settings

log = structlog.get_logger(__name__)

K8S_SA_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")


def vault_client_factory(settings: Settings) -> hvac.Client:
    client = hvac.Client(url=settings.vault_addr)
    if K8S_SA_TOKEN_PATH.exists():
        sa_token = K8S_SA_TOKEN_PATH.read_text().strip()
        client.auth.kubernetes.login(role=settings.vault_role, jwt=sa_token)
        log.info("vault auth via k8s sa", role=settings.vault_role)
    else:
        dev_token = os.environ.get("VAULT_TOKEN")
        if not dev_token:
            raise RuntimeError(
                "VAULT_TOKEN not set and no kube SA token found; "
                "set VAULT_TOKEN for local development.",
            )
        client.token = dev_token
        log.info("vault auth via VAULT_TOKEN env (dev)")
    return client
