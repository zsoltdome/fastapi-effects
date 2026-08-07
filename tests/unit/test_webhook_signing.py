from __future__ import annotations

from datetime import UTC, datetime

from standardwebhooks.webhooks import Webhook

from fastapi_mergen.webhooks.signing import sign_webhook, verify_webhook


def test_standard_webhooks_verifies_exact_body() -> None:
    secret = b"s" * 32
    body = b'{"amount":42,"event":"invoice.created"}'
    signed = sign_webhook(
        message_id="msg_delivery_42",
        timestamp=datetime.now(UTC),
        body=body,
        secrets=(secret,),
    )

    assert Webhook(secret).verify(body, dict(signed.values), json_parse=False) is None
    assert verify_webhook(secret=secret, body=body, headers=signed.values)
    assert not verify_webhook(secret=secret, body=body + b" ", headers=signed.values)


def test_rotation_overlap_adds_signatures_without_body_change() -> None:
    first = b"a" * 32
    second = b"b" * 32
    body = b"{}"
    signed = sign_webhook(
        message_id="msg_overlap",
        timestamp=datetime.now(UTC),
        body=body,
        secrets=(second, first),
    )

    assert signed.signature_count == 2
    assert len(signed.values["webhook-signature"].split()) == 2
    assert verify_webhook(secret=first, body=body, headers=signed.values)
    assert verify_webhook(secret=second, body=body, headers=signed.values)
