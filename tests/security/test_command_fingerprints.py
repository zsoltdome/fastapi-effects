from __future__ import annotations

from uuid import UUID

import pytest

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.idempotency.fingerprint import BodyFingerprintMode, fingerprint_request
from fastapi_mergen.idempotency.models import CommandIdentity

TENANT = UUID("10000000-0000-0000-0000-000000000011")


def test_canonical_json_fingerprint_is_stable_but_query_order_is_exact() -> None:
    first = fingerprint_request(
        path_parameters={"invoice_id": "inv-1"},
        raw_query=b"expand=lines&currency=EUR",
        headers={"if-match": ' "v1" '},
        media_type="Application/JSON",
        body=b'{"amount":12,"metadata":{"b":2,"a":1}}',
        mode=BodyFingerprintMode.CANONICAL_JSON,
    )
    reordered_json = fingerprint_request(
        path_parameters={"invoice_id": "inv-1"},
        raw_query=b"expand=lines&currency=EUR",
        headers={"If-Match": '"v1"'},
        media_type="application/json",
        body=b'{"metadata":{"a":1,"b":2},"amount":12}',
        mode=BodyFingerprintMode.CANONICAL_JSON,
    )
    reordered_query = fingerprint_request(
        path_parameters={"invoice_id": "inv-1"},
        raw_query=b"currency=EUR&expand=lines",
        headers={"if-match": '"v1"'},
        media_type="application/json",
        body=b'{"amount":12,"metadata":{"a":1,"b":2}}',
        mode=BodyFingerprintMode.CANONICAL_JSON,
    )
    assert first == reordered_json
    assert first != reordered_query
    assert first.hex_digest == "44610b283805e782afba613e571fe7783d437e874cc8da8b5d8be9b658661d75"


@pytest.mark.parametrize(
    "body",
    [
        b'{"a":1,"a":2}',
        b'{"value":NaN}',
        b"\xff",
        b"{",
    ],
)
def test_canonical_json_rejects_ambiguous_or_malformed_input(body: bytes) -> None:
    with pytest.raises(MergenConfigurationError):
        fingerprint_request(
            path_parameters={},
            raw_query=b"",
            headers={},
            media_type="application/json",
            body=body,
            mode=BodyFingerprintMode.CANONICAL_JSON,
        )


def test_opaque_key_is_hashed_exactly_and_never_represented() -> None:
    first = CommandIdentity.from_key(
        tenant_id=TENANT,
        route_id="invoice.create",
        method="post",
        key="opaque-key-canary",
    )
    second = CommandIdentity.from_key(
        tenant_id=TENANT,
        route_id="invoice.create",
        method="POST",
        key=b"opaque-key-canary",
    )
    assert first == second
    assert first.method == "POST"
    assert "opaque-key-canary" not in repr(first)
    with pytest.raises(MergenConfigurationError):
        CommandIdentity.from_key(
            tenant_id=TENANT,
            route_id="invoice.create",
            method="POST",
            key=b"bad\x00key",
        )


def test_fingerprint_rejects_sensitive_or_repeated_headers() -> None:
    for headers in (
        {"authorization": "Bearer canary"},
        [("if-match", "one"), ("If-Match", "two")],
    ):
        with pytest.raises(MergenConfigurationError):
            fingerprint_request(
                path_parameters={},
                raw_query=b"",
                headers=headers,
                media_type="application/json",
                body=b"{}",
                mode=BodyFingerprintMode.CANONICAL_JSON,
            )
