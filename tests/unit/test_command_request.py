from __future__ import annotations

from uuid import UUID

import pytest
from starlette.requests import Request

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.idempotency.request import prepare_request


def _request(*, body: bytes, key: bytes = b"command-1") -> Request:
    chunks = iter((body, b""))

    async def receive() -> dict[str, object]:
        chunk = next(chunks)
        return {"type": "http.request", "body": chunk, "more_body": bool(chunk)}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/invoices/1",
            "path_params": {"invoice_id": "1"},
            "query_string": b"notify=true",
            "headers": (
                (b"idempotency-key", key),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ),
        },
        receive,
    )


@pytest.mark.asyncio
async def test_preparation_retains_body_for_endpoint_parsing() -> None:
    request = _request(body=b'{"invoice":"1"}')
    prepared = await prepare_request(
        request,
        principal=Principal(
            tenant_id=UUID("10000000-0000-0000-0000-000000000011"),
            subject_id="user:alice",
        ),
        route_id="invoice.create",
    )
    assert len(prepared.identity.key_digest) == 32
    assert await request.body() == b'{"invoice":"1"}'


@pytest.mark.asyncio
async def test_preparation_rejects_missing_or_oversized_key() -> None:
    request = _request(body=b"{}", key=b"x" * 513)
    with pytest.raises(MergenConfigurationError):
        await prepare_request(
            request,
            principal=Principal(
                tenant_id=UUID("10000000-0000-0000-0000-000000000011"),
                subject_id="user:alice",
            ),
            route_id="invoice.create",
        )
