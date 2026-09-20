"""FastAPI dependency for exact target-bound delegation enforcement."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request, status

from fastapi_effects.core.principal import Principal
from fastapi_effects.delegation.audit import delegation_target_id
from fastapi_effects.delegation.models import DelegationClaims
from fastapi_effects.delegation.signing import DelegationVerifier
from fastapi_effects.errors import AuthorizationDenied


@dataclass(frozen=True, slots=True)
class VerifiedDelegation:
    principal: Principal
    issuer: str
    audience: str
    target_id: str
    token_id: UUID
    key_id: str
    delegation_depth: int


def verified_delegation_dependency(
    verifier: DelegationVerifier,
    *,
    audience: str,
    required_scopes: frozenset[str],
    route_allowed_scopes: frozenset[str] | None = None,
    header_name: str = "FastAPI-Effects-Delegation",
) -> Callable[[Request], Awaitable[VerifiedDelegation]]:
    authority_ceiling = required_scopes if route_allowed_scopes is None else route_allowed_scopes

    async def dependency(request: Request) -> VerifiedDelegation:
        token = request.headers.get(header_name)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="delegation credential required",
            )
        try:
            claims = verifier.verify(
                token=token,
                audience=audience,
                method=request.method,
                path=request.url.path,
                required_scopes=required_scopes,
                authority_ceiling=authority_ceiling,
                trace_id=_trace_id(request),
            )
        except AuthorizationDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="delegation credential denied",
            ) from exc
        verified = _verified(claims)
        request.state.fastapi_effects_delegation = verified
        return verified

    return dependency


def delegated_principal_dependency(
    verifier: DelegationVerifier,
    *,
    audience: str,
    required_scopes: frozenset[str],
    route_allowed_scopes: frozenset[str] | None = None,
    header_name: str = "FastAPI-Effects-Delegation",
) -> Callable[[Request], Awaitable[Principal]]:
    verified_dependency = verified_delegation_dependency(
        verifier,
        audience=audience,
        required_scopes=required_scopes,
        route_allowed_scopes=route_allowed_scopes,
        header_name=header_name,
    )

    async def dependency(request: Request) -> Principal:
        return (await verified_dependency(request)).principal

    return dependency


def _verified(claims: DelegationClaims) -> VerifiedDelegation:
    principal = Principal(
        tenant_id=claims.tenant_id,
        subject_id=claims.subject_id,
        actor_id=claims.actor_id,
        client_id=claims.client_id,
        scopes=frozenset(claims.scopes),
        issued_at=claims.issued_at,
        expires_at=claims.expires_at,
        credential_ref=f"delegation:{claims.token_id}",
    )
    return VerifiedDelegation(
        principal=principal,
        issuer=claims.issuer,
        audience=claims.audience,
        target_id=delegation_target_id(claims.method, claims.path),
        token_id=claims.token_id,
        key_id=claims.key_id,
        delegation_depth=claims.delegation_depth,
    )


def _trace_id(request: Request) -> str | None:
    value = request.headers.get("traceparent")
    if value is None:
        return None
    parts = value.split("-")
    if len(parts) == 4 and len(parts[1]) == 32:
        try:
            int(parts[1], 16)
        except ValueError:
            return None
        return parts[1]
    return None


__all__ = [
    "VerifiedDelegation",
    "delegated_principal_dependency",
    "verified_delegation_dependency",
]
