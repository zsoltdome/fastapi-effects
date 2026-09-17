from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from examples.webhook_receiver import app as receiver
from fastapi_mergen.webhooks.signing import sign_webhook


def _encode(value: bytes) -> str:
    return "whsec_" + base64.b64encode(value).decode("ascii")


@pytest.mark.asyncio
async def test_receiver_accepts_rotation_overlap_and_deduplicates_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = b"o" * 32
    current = b"n" * 32
    monkeypatch.delenv("WEBHOOK_SIGNING_SECRET", raising=False)
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRETS", f"{_encode(old)},{_encode(current)}")
    receiver._processed.clear()
    body = b'{"event":"invoice.created"}'
    headers = dict(
        sign_webhook(
            message_id="msg_rotation_1",
            timestamp=datetime.now(UTC),
            body=body,
            secrets=(current,),
        ).values
    )

    async with AsyncClient(
        transport=ASGITransport(app=receiver.app),
        base_url="http://receiver.test",
    ) as client:
        first = await client.post("/hooks", content=body, headers=headers)
        retry = await client.post("/hooks", content=body, headers=headers)

    assert first.json()["duplicate"] is False
    assert retry.json()["duplicate"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [timedelta(seconds=-301), timedelta(seconds=301)])
async def test_receiver_rejects_stale_and_excessive_future_packets(
    monkeypatch: pytest.MonkeyPatch,
    offset: timedelta,
) -> None:
    secret = b"t" * 32
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", _encode(secret))
    monkeypatch.delenv("WEBHOOK_SIGNING_SECRETS", raising=False)
    body = b"{}"
    headers = dict(
        sign_webhook(
            message_id="msg_old_or_future",
            timestamp=datetime.now(UTC) + offset,
            body=body,
            secrets=(secret,),
        ).values
    )

    async with AsyncClient(
        transport=ASGITransport(app=receiver.app),
        base_url="http://receiver.test",
    ) as client:
        response = await client.post("/hooks", content=body, headers=headers)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_receiver_rejects_duplicate_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"h" * 32
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", _encode(secret))
    body = b"{}"
    signed = sign_webhook(
        message_id="msg_duplicate_header",
        timestamp=datetime.now(UTC),
        body=body,
        secrets=(secret,),
    )
    headers = list(signed.values.items())
    headers.append(("webhook-id", "msg_duplicate_header"))

    async with AsyncClient(
        transport=ASGITransport(app=receiver.app),
        base_url="http://receiver.test",
    ) as client:
        response = await client.post("/hooks", content=body, headers=headers)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_receiver_streams_and_rejects_body_over_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"b" * 32
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", _encode(secret))
    monkeypatch.setenv("WEBHOOK_MAX_BODY_BYTES", "4")
    body = b"12345"
    headers = dict(
        sign_webhook(
            message_id="msg_oversized",
            timestamp=datetime.now(UTC),
            body=body,
            secrets=(secret,),
        ).values
    )
    headers["content-length"] = "1"

    async with AsyncClient(
        transport=ASGITransport(app=receiver.app),
        base_url="http://receiver.test",
    ) as client:
        response = await client.post("/hooks", content=body, headers=headers)

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_receiver_rejects_same_message_id_with_conflicting_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"c" * 32
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", _encode(secret))
    receiver._processed.clear()
    now = datetime.now(UTC)

    async with AsyncClient(
        transport=ASGITransport(app=receiver.app),
        base_url="http://receiver.test",
    ) as client:
        for body, expected in ((b"first", 200), (b"second", 409)):
            headers = dict(
                sign_webhook(
                    message_id="msg_conflict",
                    timestamp=now,
                    body=body,
                    secrets=(secret,),
                ).values
            )
            response = await client.post("/hooks", content=body, headers=headers)
            assert response.status_code == expected
