"""Charge endpoints.

Authentication: JWT verified against identity-svc JWKS.
Authorization: scope-gated; customer_id must match resource owner.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from payments_api.auth import AuthError, TokenClaims, verify_token

router = APIRouter()
log = structlog.get_logger(__name__)


class ChargeRequest(BaseModel):
    amount_cents: int = Field(..., ge=1, le=10_000_000)
    currency: str = Field(..., min_length=3, max_length=3)
    customer_id: str
    description: str | None = None
    idempotency_key: str


class ChargeResponse(BaseModel):
    id: str
    status: str
    amount_cents: int
    currency: str


async def _claims(authorization: str | None = Header(default=None),
                  required_scope: str = "charges:read") -> TokenClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        return await verify_token(token, require_scopes=[required_scope])
    except AuthError as exc:
        raise HTTPException(403, str(exc))


@router.post("", response_model=ChargeResponse)
async def create_charge(req: ChargeRequest,
                        request: Request,
                        claims: TokenClaims = Depends(_claims)) -> ChargeResponse:
    if claims.customer_id != req.customer_id:
        raise HTTPException(403, "customer_id mismatch")
    if not claims.has_scope("charges:write"):
        raise HTTPException(403, "missing scope charges:write")

    stripe = request.app.state.stripe
    charge = stripe.charges.create(
        amount=req.amount_cents,
        currency=req.currency,
        description=req.description,
        idempotency_key=req.idempotency_key,
    )
    log.info("charge created",
             charge_id=charge.id,
             customer_id=req.customer_id,
             amount_cents=req.amount_cents)
    return ChargeResponse(
        id=charge.id,
        status=charge.status,
        amount_cents=charge.amount,
        currency=charge.currency,
    )


@router.get("/{charge_id}", response_model=ChargeResponse)
async def get_charge(charge_id: str,
                     request: Request,
                     claims: TokenClaims = Depends(_claims)) -> ChargeResponse:
    stripe = request.app.state.stripe
    charge = stripe.charges.retrieve(charge_id)
    # XXX(sam): we should check that customer_id matches. HELIX-2089.
    return ChargeResponse(
        id=charge.id,
        status=charge.status,
        amount_cents=charge.amount,
        currency=charge.currency,
    )
