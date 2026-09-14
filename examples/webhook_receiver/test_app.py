from __future__ import annotations

import base64
from datetime import UTC, datetime

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
