"""FastAPI entrypoint for payments-api."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from payments_api.config import settings
from payments_api.routes import charges, health
from payments_api.stripe_client import stripe_client_factory
from payments_api.vault import vault_client_factory

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("payments-api starting",
             env=settings.environment,
             commit=settings.commit_sha)
    app.state.vault = vault_client_factory(settings)
    app.state.stripe = stripe_client_factory(settings, app.state.vault)
    yield
    log.info("payments-api shutting down")


app = FastAPI(title="Helix Payments API", lifespan=lifespan)
app.include_router(health.router)
app.include_router(charges.router, prefix="/charges", tags=["charges"])
app.mount("/metrics", make_asgi_app())
