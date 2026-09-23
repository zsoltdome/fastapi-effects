"""Conformance adapter for the production delegation bridge and verifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi_effects.conformance.contract import Capability, Invariant
from fastapi_effects.conformance.manifest import CapabilityManifest
from fastapi_effects.conformance.protocols import (
    ConformanceAccessDenied,
    DelegationView,
)
from fastapi_effects.core.principal import Principal
from fastapi_effects.delegation.audit import DelegationAuditEvent
from fastapi_effects.delegation.bridge import DelegationBridge, TrustedCallerMetadata
from fastapi_effects.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_effects.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_effects.errors import AuthorizationDenied


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 25, 12, 5, tzinfo=UTC)


class _Audit:
    def __init__(self) -> None:
        self.events: list[DelegationAuditEvent] = []

    def record(self, event: DelegationAuditEvent) -> None:
        self.events.append(event)


class RealDelegationBoundaryDriver:
    def __init__(self) -> None:
        audit = _Audit()
        keys = InMemoryKeyRing((SigningKey("conformance-key", b"d" * 32),), audit=audit)
        issuer = DelegationIssuer(
            issuer="conformance-gateway",
            keys=keys,
            clock=_Clock(),
            audit=audit,
        )
        self._bridge = DelegationBridge(
            issuer,
            allowed_scopes=frozenset({"billing:read", "billing:write"}),
        )
        self._verifier = DelegationVerifier(
            issuer="conformance-gateway",
            keys=keys,
            clock=_Clock(),
            allowed_scopes=frozenset({"billing:read", "billing:write"}),
            audit=audit,
        )
        self._audit = audit

    @property
    def manifest(self) -> CapabilityManifest:
        return CapabilityManifest(
            adapter_name="fastapi_effects_delegation",
            adapter_version="0.11.0a2",
            implementation=(
                "fastapi_effects.testing.delegation_driver.RealDelegationBoundaryDriver"
            ),
            capabilities=frozenset({Capability.DELEGATION}),
            invariants=frozenset({Invariant.SECRET_MINIMIZATION, Invariant.DELEGATION_BINDING}),
            metadata={"signing": "hmac-sha256", "bridge": "target-bound"},
        )

    async def reset(self) -> None:
        self._audit.events.clear()

    async def close(self) -> None:
        return None

    async def public_evidence(self) -> dict[str, int]:
        return {"delegation_audit_events": len(self._audit.events)}

    async def mint_delegation(
        self,
        *,
        principal: Principal,
        audience: str,
        method: str,
        path: str,
        scopes: frozenset[str],
        ttl: timedelta,
    ) -> str:
        request = self._bridge.prepare_trusted(
            caller=TrustedCallerMetadata(
                principal=principal,
                authentication_source="conformance.host",
            ),
            audience=audience,
            method=method,
            path=path,
            requested_scopes=scopes,
            inbound_headers={
                "Authorization": "Bearer conformance-secret-canary",
                "Cookie": "session-cookie-canary",
            },
            ttl=ttl,
        )
        return request.headers["FastAPI-Effects-Delegation"]

    async def verify_delegation(
        self,
        *,
        token: str,
        audience: str,
        method: str,
        path: str,
        required_scopes: frozenset[str],
    ) -> DelegationView:
        try:
            claims = self._verifier.verify(
                token=token,
                audience=audience,
                method=method,
                path=path,
                required_scopes=required_scopes,
                authority_ceiling=frozenset({"billing:read", "billing:write"}),
            )
        except AuthorizationDenied as exc:
            raise ConformanceAccessDenied from exc
        return DelegationView(
            tenant_id=claims.tenant_id,
            subject_id=claims.subject_id,
            actor_id=claims.actor_id,
            client_id=claims.client_id,
            scopes=frozenset(claims.scopes),
            audience=claims.audience,
            method=claims.method,
            path=claims.path,
        )


__all__ = ["RealDelegationBoundaryDriver"]
