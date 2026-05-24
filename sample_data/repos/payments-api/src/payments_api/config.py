"""Environment-driven settings.

Secrets are NOT pulled from env vars — they come from Vault at startup
via vault.py. Env carries only the Vault endpoint + role.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str
    commit_sha: str

    vault_addr: str
    vault_role: str

    pii_vault_url: str
    identity_jwks_url: str

    database_url: str          # populated post-Vault-bootstrap; placeholder here
    stripe_account_id: str     # account-id, not key — keys via Vault

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.environ.get("ENV", "dev"),
            commit_sha=os.environ.get("COMMIT_SHA", "dev"),
            vault_addr=os.environ.get("VAULT_ADDR", "https://vault.helix.internal:8200"),
            vault_role=os.environ.get("VAULT_ROLE", "payments-api"),
            pii_vault_url=os.environ.get("PII_VAULT_URL", "https://pii.helix.internal"),
            identity_jwks_url=os.environ.get(
                "IDENTITY_JWKS_URL",
                "https://auth.helix.io/.well-known/jwks.json",
            ),
            database_url="",
            stripe_account_id=os.environ.get("STRIPE_ACCOUNT_ID", "acct_unset"),
        )


settings = Settings.from_env()
