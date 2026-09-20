"""FastMCP-facing delegation bridge without credential forwarding.

The host supplies already-authenticated caller metadata. This module deliberately
does not import FastMCP at module import time, keeping the base package isolated.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol

from fastapi_effects.delegation.bridge import (
    DelegatedRequest,
    DelegationBridge,
    TrustedCallerMetadata,
)


class AsyncDownstreamClient(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: object,
    ) -> object: ...


class FastMCPDelegationBridge(DelegationBridge):
    """Dispatch from a FastMCP tool using only host-verified caller metadata."""

    async def dispatch(
        self,
        client: AsyncDownstreamClient,
        *,
        caller: TrustedCallerMetadata,
        audience: str,
        method: str,
        path: str,
        requested_scopes: frozenset[str],
        json_body: object,
        inbound_headers: Mapping[str, str] | None = None,
        ttl: timedelta = timedelta(minutes=2),
        trace_id: str | None = None,
    ) -> object:
        delegated = self.prepare_trusted(
            caller=caller,
            audience=audience,
            method=method,
            path=path,
            requested_scopes=requested_scopes,
            inbound_headers=inbound_headers,
            ttl=ttl,
            trace_id=trace_id,
        )
        return await client.request(
            delegated.method,
            delegated.path,
            headers=delegated.headers,
            json=json_body,
        )


__all__ = [
    "AsyncDownstreamClient",
    "DelegatedRequest",
    "FastMCPDelegationBridge",
    "TrustedCallerMetadata",
]
