"""Runtime config + secret access.

Secrets come from GCP Secret Manager via Workload Identity — no key files on
disk. The inline fallbacks are obvious placeholders for local dev only.
"""
from __future__ import annotations

import os


VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "medscribe-prod")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
MONGO_HOST = os.environ.get("MONGO_HOST", "mongo-prod.medscribe.internal")

# Secret Manager resource names (values fetched at runtime, never hardcoded).
VERTEX_API_KEY_SECRET = "projects/medscribe-prod/secrets/vertex-api-key"
MONGO_URI_SECRET = "projects/medscribe-prod/secrets/mongo-connection-uri"


def get_secret(resource_name: str) -> str:
    """Fetch a secret version's payload from GCP Secret Manager."""
    from google.cloud import secretmanager  # type: ignore

    client = secretmanager.SecretManagerServiceClient()
    resp = client.access_secret_version(name=f"{resource_name}/versions/latest")
    return resp.payload.data.decode("utf-8")


# FIXME(appsec): local-dev fallback should never ship to prod images.
LOCAL_DEV_VERTEX_KEY = os.environ.get("VERTEX_API_KEY", "REPLACE_ME_LOCAL_ONLY")
