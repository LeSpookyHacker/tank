"""Stripe SDK wrapper.

Stripe restricted-key lookup goes through Vault. We never read keys
from env vars.
"""
from __future__ import annotations

import structlog
import stripe

from payments_api.config import Settings

log = structlog.get_logger(__name__)


def stripe_client_factory(settings: Settings, vault) -> stripe.StripeClient:
    secret_path = f"secret/payments-api/{settings.environment}/stripe-restricted-key"
    resp = vault.secrets.kv.v2.read_secret_version(path=secret_path)
    api_key = resp["data"]["data"]["key"]
    log.info("stripe client initialized",
             account=settings.stripe_account_id,
             env=settings.environment)
    return stripe.StripeClient(api_key=api_key)
