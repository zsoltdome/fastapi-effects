"""Issue next-hop credentials from trusted host-authentication metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.delegation.signing import DelegationIssuer
from fastapi_mergen.errors import MergenConfigurationError

_CREDENTIAL_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-session-id",
        "x-session-token",
    }
)
_HEADER_NAME = re.compile(r"^[a-z0-9!#$%&'*+\-.^_`|~]{1,128}$")
_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class DelegatedRequest:
    method: str
    path: str
    headers: Mapping[str, str] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class TrustedCallerMetadata:
    """Identity asserted by host authentication, never constructed from tool arguments."""

    principal: Principal
    authentication_source: str
    delegation_depth: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.principal, Principal):
            raise MergenConfigurationError("Trusted caller principal is invalid.")
        if not isinstance(self.authentication_source, str) or not _SOURCE.fullmatch(
            self.authentication_source
        ):
            raise MergenConfigurationError("Trusted caller authentication source is invalid.")
        if (
            not isinstance(self.delegation_depth, int)
            or isinstance(self.delegation_depth, bool)
            or not 0 <= self.delegation_depth < 16
        ):
            raise MergenConfigurationError("Trusted caller delegation depth is invalid.")


class DelegationBridge:
    def __init__(
        self,
        issuer: DelegationIssuer,
        *,
        allowed_scopes: frozenset[str],
        header_name: str = "Mergen-Delegation",
        forwarded_headers: frozenset[str] = frozenset({"traceparent", "tracestate"}),
    ) -> None:
        if not isinstance(forwarded_headers, frozenset):
            raise MergenConfigurationError("Delegation bridge policy is invalid.")
        normalized_forwarded = frozenset(name.lower() for name in forwarded_headers)
        if (
            not isinstance(allowed_scopes, frozenset)
            or any(
                not isinstance(scope, str) or not _SCOPE.fullmatch(scope)
                for scope in allowed_scopes
            )
            or any(
                not isinstance(name, str)
                or not _HEADER_NAME.fullmatch(name)
                or name in _CREDENTIAL_HEADERS
                or "session" in name
                or "token" in name
                or "key" in name
                for name in normalized_forwarded
            )
        ):
            raise MergenConfigurationError("Delegation bridge policy is invalid.")
        if (
            not isinstance(header_name, str)
            or not _HEADER_NAME.fullmatch(header_name.lower())
            or header_name.lower() in _CREDENTIAL_HEADERS
        ):
            raise MergenConfigurationError("Delegation header name is invalid.")
        self._issuer = issuer
        self._allowed_scopes = allowed_scopes
        self._header_name = header_name
        self._forwarded_headers = normalized_forwarded

    def prepare_trusted(
        self,
        *,
        caller: TrustedCallerMetadata,
        audience: str,
        method: str,
        path: str,
        requested_scopes: frozenset[str],
        inbound_headers: Mapping[str, str] | None = None,
        ttl: timedelta = timedelta(minutes=2),
        trace_id: str | None = None,
    ) -> DelegatedRequest:
        return self.prepare(
            principal=caller.principal,
            audience=audience,
            method=method,
            path=path,
            requested_scopes=requested_scopes,
            inbound_headers=inbound_headers,
            ttl=ttl,
            parent_depth=caller.delegation_depth,
            trace_id=trace_id,
        )

    def prepare(
        self,
        *,
        principal: Principal,
        audience: str,
        method: str,
        path: str,
        requested_scopes: frozenset[str],
        inbound_headers: Mapping[str, str] | None = None,
        ttl: timedelta = timedelta(minutes=2),
        parent_depth: int = 0,
        trace_id: str | None = None,
    ) -> DelegatedRequest:
        if not isinstance(requested_scopes, frozenset):
            raise MergenConfigurationError("Delegation requested scopes are invalid.")
        effective = requested_scopes & principal.scopes & self._allowed_scopes
        if effective != requested_scopes:
            raise MergenConfigurationError("Delegation component policy denied requested scopes.")
        safe_headers: dict[str, str] = {}
        for key, value in (inbound_headers or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise MergenConfigurationError("Delegation inbound header is invalid.")
            normalized = key.lower()
            if normalized not in self._forwarded_headers:
                continue
            if len(value) > 1024 or any(character in value for character in "\r\n\x00"):
                raise MergenConfigurationError("Delegation forwarded header is invalid.")
            safe_headers[key] = value
        token = self._issuer.mint(
            principal=principal,
            audience=audience,
            method=method,
            path=path,
            scopes=effective,
            ttl=ttl,
            parent_depth=parent_depth,
            trace_id=trace_id,
        )
        safe_headers[self._header_name] = token
        return DelegatedRequest(method=method, path=path, headers=safe_headers)


__all__ = ["DelegatedRequest", "DelegationBridge", "TrustedCallerMetadata"]
