"""HMAC-SHA-256 issuance and exact target-bound verification."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi_effects.core.identity import UUIDSource
from fastapi_effects.core.principal import Principal
from fastapi_effects.core.protocols import Clock, UUIDGenerator
from fastapi_effects.core.runtime import SystemClock
from fastapi_effects.delegation.audit import (
    DelegationAuditEvent,
    DelegationAuditOutcome,
    NoOpDelegationAuditSink,
    delegation_target_id,
)
from fastapi_effects.delegation.encoding import claims_bytes, decode_token, encode_token
from fastapi_effects.delegation.models import DelegationClaims
from fastapi_effects.delegation.protocols import DelegationAuditSink, DelegationKeyRing
from fastapi_effects.delegation.targets import canonical_method, canonical_target_path
from fastapi_effects.errors import AuthorizationDenied, FastAPIEffectsConfigurationError

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class DelegationIssuer:
    issuer: str
    keys: DelegationKeyRing
    clock: Clock = field(default_factory=SystemClock)
    uuid_source: UUIDGenerator = field(default_factory=UUIDSource)
    audit: DelegationAuditSink = field(default_factory=NoOpDelegationAuditSink)
    maximum_ttl_seconds: int = 300
    maximum_depth: int = 4

    def __post_init__(self) -> None:
        _configuration(self.issuer, self.maximum_ttl_seconds, self.maximum_depth)

    def mint(
        self,
        *,
        principal: Principal,
        audience: str,
        method: str,
        path: str,
        scopes: frozenset[str],
        ttl: timedelta,
        parent_depth: int = 0,
        trace_id: str | None = None,
    ) -> str:
        if not isinstance(principal, Principal):
            raise FastAPIEffectsConfigurationError("Delegation requires a trusted principal.")
        if not isinstance(scopes, frozenset) or not scopes.issubset(principal.scopes):
            raise FastAPIEffectsConfigurationError(
                "Delegation scopes exceed the verified principal."
            )
        if (
            not isinstance(parent_depth, int)
            or isinstance(parent_depth, bool)
            or not 0 <= parent_depth < self.maximum_depth
        ):
            raise FastAPIEffectsConfigurationError("Delegation parent depth is invalid.")
        seconds = ttl.total_seconds() if isinstance(ttl, timedelta) else -1
        if seconds <= 0 or seconds > self.maximum_ttl_seconds or not seconds.is_integer():
            raise FastAPIEffectsConfigurationError("Delegation TTL is invalid.")
        depth = parent_depth + 1
        if depth > self.maximum_depth:
            raise FastAPIEffectsConfigurationError("Delegation depth exceeds configured policy.")
        now = self.clock.now()
        expiry = now + ttl
        if principal.expires_at is not None and expiry > principal.expires_at:
            expiry = principal.expires_at
        if expiry <= now:
            raise FastAPIEffectsConfigurationError("Delegation principal is expired.")
        key = self.keys.signing_key(now)
        claims = DelegationClaims(
            version=1,
            issuer=self.issuer,
            tenant_id=principal.tenant_id,
            subject_id=principal.subject_id,
            actor_id=principal.actor_id,
            client_id=principal.client_id,
            audience=audience,
            method=canonical_method(method),
            path=canonical_target_path(path),
            scopes=tuple(scopes),
            issued_at=now,
            not_before=now,
            expires_at=expiry,
            token_id=self.uuid_source.new_uuid(),
            key_id=key.key_id,
            delegation_depth=depth,
        )
        payload = claims_bytes(claims)
        signature = hmac.new(key.secret, payload, hashlib.sha256).digest()
        token = encode_token(payload, signature)
        self.audit.record(
            _audit_event(
                claims=claims,
                occurred_at=now,
                outcome=DelegationAuditOutcome.ISSUED,
                trace_id=trace_id,
            )
        )
        return token


@dataclass(frozen=True, slots=True)
class DelegationVerifier:
    issuer: str
    keys: DelegationKeyRing
    clock: Clock = field(default_factory=SystemClock)
    allowed_scopes: frozenset[str] | None = None
    audit: DelegationAuditSink = field(default_factory=NoOpDelegationAuditSink)
    maximum_ttl_seconds: int = 300
    maximum_depth: int = 4
    clock_skew_seconds: int = 5

    def __post_init__(self) -> None:
        _configuration(self.issuer, self.maximum_ttl_seconds, self.maximum_depth)
        if (
            not isinstance(self.clock_skew_seconds, int)
            or isinstance(self.clock_skew_seconds, bool)
            or not 0 <= self.clock_skew_seconds <= 60
        ):
            raise FastAPIEffectsConfigurationError("Delegation verifier clock skew is invalid.")
        if self.allowed_scopes is not None and (
            not isinstance(self.allowed_scopes, frozenset)
            or len(self.allowed_scopes) > 128
            or any(
                not isinstance(scope, str) or not _SCOPE.fullmatch(scope)
                for scope in self.allowed_scopes
            )
        ):
            raise FastAPIEffectsConfigurationError("Delegation verifier scope ceiling is invalid.")

    def verify(
        self,
        *,
        token: str,
        audience: str,
        method: str,
        path: str,
        required_scopes: frozenset[str],
        authority_ceiling: frozenset[str] | None = None,
        trace_id: str | None = None,
    ) -> DelegationClaims:
        claims: DelegationClaims | None = None
        now = self.clock.now()
        target_id = delegation_target_id(method, path)
        try:
            if (
                not isinstance(audience, str)
                or not _IDENTIFIER.fullmatch(audience)
                or not isinstance(required_scopes, frozenset)
                or len(required_scopes) > 128
                or any(
                    not isinstance(scope, str) or not _SCOPE.fullmatch(scope)
                    for scope in required_scopes
                )
                or (
                    authority_ceiling is not None
                    and (
                        not isinstance(authority_ceiling, frozenset)
                        or len(authority_ceiling) > 128
                        or any(
                            not isinstance(scope, str) or not _SCOPE.fullmatch(scope)
                            for scope in authority_ceiling
                        )
                    )
                )
            ):
                raise AuthorizationDenied("Delegation credential was rejected.")
            expected_method = canonical_method(method)
            expected_path = canonical_target_path(path)
            claims, payload, signature = decode_token(token)
            key = self.keys.verification_key(claims.key_id, now)
            if key is None:
                raise AuthorizationDenied("Delegation credential was rejected.")
            expected = hmac.new(key.secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(expected, signature):
                raise AuthorizationDenied("Delegation credential was rejected.")
            skew = timedelta(seconds=self.clock_skew_seconds)
            if (
                claims.issuer != self.issuer
                or claims.audience != audience
                or claims.method != expected_method
                or claims.path != expected_path
                or claims.not_before > now + skew
                or claims.issued_at > now + skew
                or claims.expires_at <= now - skew
                or (claims.expires_at - claims.issued_at).total_seconds() > self.maximum_ttl_seconds
                or claims.delegation_depth > self.maximum_depth
                or not required_scopes.issubset(claims.scopes)
                or (
                    authority_ceiling is not None
                    and not frozenset(claims.scopes).issubset(authority_ceiling)
                )
                or (
                    self.allowed_scopes is not None
                    and not frozenset(claims.scopes).issubset(self.allowed_scopes)
                )
            ):
                raise AuthorizationDenied("Delegation credential was rejected.")
        except AuthorizationDenied:
            self.audit.record(
                _denied_event(
                    now=now,
                    audience=audience,
                    target_id=target_id,
                    required_scopes=required_scopes,
                    claims=claims,
                    trace_id=trace_id,
                )
            )
            raise
        except Exception as exc:
            self.audit.record(
                _denied_event(
                    now=now,
                    audience=audience,
                    target_id=target_id,
                    required_scopes=required_scopes,
                    claims=claims,
                    trace_id=trace_id,
                )
            )
            raise AuthorizationDenied("Delegation credential was rejected.") from exc
        self.audit.record(
            _audit_event(
                claims=claims,
                occurred_at=now,
                outcome=DelegationAuditOutcome.ALLOWED,
                trace_id=trace_id,
            )
        )
        return claims


def _configuration(issuer: object, maximum_ttl_seconds: object, maximum_depth: object) -> None:
    if not isinstance(issuer, str) or not _IDENTIFIER.fullmatch(issuer):
        raise FastAPIEffectsConfigurationError("Delegation issuer configuration is invalid.")
    if (
        not isinstance(maximum_ttl_seconds, int)
        or isinstance(maximum_ttl_seconds, bool)
        or not 1 <= maximum_ttl_seconds <= 3600
    ):
        raise FastAPIEffectsConfigurationError("Delegation maximum TTL is invalid.")
    if (
        not isinstance(maximum_depth, int)
        or isinstance(maximum_depth, bool)
        or not 1 <= maximum_depth <= 16
    ):
        raise FastAPIEffectsConfigurationError("Delegation maximum depth is invalid.")


def _audit_event(
    *,
    claims: DelegationClaims,
    occurred_at: datetime,
    outcome: DelegationAuditOutcome,
    trace_id: str | None,
) -> DelegationAuditEvent:
    return DelegationAuditEvent(
        occurred_at=occurred_at,
        outcome=outcome,
        tenant_id=claims.tenant_id,
        subject_id=claims.subject_id,
        actor_id=claims.actor_id,
        client_id=claims.client_id,
        token_id=claims.token_id,
        audience=claims.audience,
        target_id=delegation_target_id(claims.method, claims.path),
        scopes=claims.scopes,
        key_id=claims.key_id,
        delegation_depth=claims.delegation_depth,
        trace_id=trace_id,
    )


def _denied_event(
    *,
    now: datetime,
    audience: object,
    target_id: str,
    required_scopes: object,
    claims: DelegationClaims | None,
    trace_id: str | None,
) -> DelegationAuditEvent:
    safe_audience = (
        audience
        if isinstance(audience, str) and _IDENTIFIER.fullmatch(audience)
        else "invalid-audience"
    )
    safe_scopes = (
        tuple(required_scopes)
        if isinstance(required_scopes, frozenset)
        and all(isinstance(scope, str) and _SCOPE.fullmatch(scope) for scope in required_scopes)
        else ()
    )
    return DelegationAuditEvent(
        occurred_at=now,
        outcome=DelegationAuditOutcome.DENIED,
        tenant_id=None if claims is None else claims.tenant_id,
        subject_id=None if claims is None else claims.subject_id,
        actor_id=None if claims is None else claims.actor_id,
        client_id=None if claims is None else claims.client_id,
        token_id=None if claims is None else claims.token_id,
        audience=safe_audience,
        target_id=target_id,
        scopes=safe_scopes,
        key_id=None if claims is None else claims.key_id,
        delegation_depth=None if claims is None else claims.delegation_depth,
        trace_id=trace_id,
    )


__all__ = ["DelegationIssuer", "DelegationVerifier"]
