from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi_mergen import Principal
from fastapi_mergen.delegation.bridge import DelegationBridge
from fastapi_mergen.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_mergen.delegation.signing import DelegationIssuer


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def test_bridge_strips_inbound_credentials_and_attenuates_scopes() -> None:
    bridge = DelegationBridge(
        DelegationIssuer(
            issuer="mcp-gateway",
            keys=InMemoryKeyRing((SigningKey("key-v1", b"s" * 32),)),
            clock=FixedClock(),
        ),
        allowed_scopes=frozenset({"billing:read"}),
    )
    request = bridge.prepare(
        principal=Principal(
            tenant_id=uuid4(),
            subject_id="user:42",
            scopes=frozenset({"billing:read", "admin"}),
            issued_at=FixedClock().now(),
        ),
        audience="billing-api",
        method="GET",
        path="/v1/invoices/42",
        requested_scopes=frozenset({"billing:read"}),
        inbound_headers={
            "Authorization": "Bearer origin-canary",
            "Cookie": "session=origin-canary",
            "X-Session-Token": "origin-session-canary",
            "X-Untrusted": "origin-arbitrary-canary",
            "Traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        },
    )
    lowered = {key.lower(): value for key, value in request.headers.items()}
    assert "authorization" not in lowered
    assert "cookie" not in lowered
    assert "origin-canary" not in repr(request)
    assert "mrg1." not in repr(request)
    assert "x-session-token" not in lowered
    assert "x-untrusted" not in lowered
    assert "mergen-delegation" in lowered
