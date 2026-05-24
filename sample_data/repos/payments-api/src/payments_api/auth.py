"""JWT verification against identity-svc's JWKS.

Cache JWKS for 4 hours. Verify signature (HS256 — TODO: move to RS256
per HELIX-1981 follow-up). Enforce aud, scope, customer_id.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import httpx
import structlog
from jose import jwt
from jose.exceptions import JWTError

from payments_api.config import settings

log = structlog.get_logger(__name__)

_JWKS_CACHE: tuple[float, dict] | None = None
_JWKS_TTL = 4 * 60 * 60


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    customer_id: str
    scopes: frozenset[str]
    iss: str
    aud: list[str]
    exp: int

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


async def _fetch_jwks() -> dict:
    global _JWKS_CACHE
    now = time.monotonic()
    if _JWKS_CACHE is not None:
        cached_at, jwks = _JWKS_CACHE
        if now - cached_at < _JWKS_TTL:
            return jwks
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(settings.identity_jwks_url)
        r.raise_for_status()
        jwks = r.json()
    _JWKS_CACHE = (now, jwks)
    return jwks


async def verify_token(token: str, *, require_scopes: Iterable[str]) -> TokenClaims:
    jwks = await _fetch_jwks()
    try:
        claims = jwt.decode(
            token, jwks, algorithms=["HS256"],
            audience="payments-api",
            issuer="https://auth.helix.io",
        )
    except JWTError as exc:
        log.warning("jwt verify failed", error=str(exc))
        raise AuthError("invalid token") from exc

    scopes = frozenset(claims.get("scope", "").split())
    for required in require_scopes:
        if required not in scopes:
            raise AuthError(f"missing scope {required}")

    return TokenClaims(
        sub=claims["sub"],
        customer_id=claims["customer_id"],
        scopes=scopes,
        iss=claims["iss"],
        aud=claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]],
        exp=int(claims["exp"]),
    )
