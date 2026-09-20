from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest
from standardwebhooks.webhooks import Webhook

from fastapi_effects.webhooks.signing import sign_webhook, verify_webhook


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


@pytest.mark.parametrize(
    ("offset", "accepted"),
    [
        (timedelta(seconds=-301), False),
        (timedelta(seconds=-300), True),
        (timedelta(seconds=300), True),
        (timedelta(seconds=301), False),
    ],
)
def test_verification_enforces_deterministic_freshness_boundaries(
    offset: timedelta,
    accepted: bool,
) -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    secret = b"f" * 32
    body = b"{}"
    signed = sign_webhook(
        message_id="msg_freshness",
        timestamp=now + offset,
        body=body,
        secrets=(secret,),
    )

    assert verify_webhook(secret=secret, body=body, headers=signed.values, now=now) is accepted


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("webhook-id", "bad id"),
        ("webhook-timestamp", "-1"),
        ("webhook-timestamp", "1.5"),
        ("webhook-timestamp", "9" * 17),
        ("webhook-signature", "v1,not-base64!"),
        ("webhook-signature", "v2," + base64.b64encode(b"x" * 32).decode()),
    ],
)
def test_verification_rejects_malformed_external_headers(header: str, value: str) -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    secret = b"m" * 32
    signed = sign_webhook(
        message_id="msg_malformed",
        timestamp=now,
        body=b"{}",
        secrets=(secret,),
    )
    headers = dict(signed.values)
    headers[header] = value

    assert not verify_webhook(secret=secret, body=b"{}", headers=headers, now=now)


def test_verification_rejects_case_insensitive_duplicate_security_headers() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    secret = b"d" * 32
    headers = dict(
        sign_webhook(
            message_id="msg_duplicate",
            timestamp=now,
            body=b"{}",
            secrets=(secret,),
        ).values
    )
    headers["Webhook-ID"] = headers["webhook-id"]

    assert not verify_webhook(secret=secret, body=b"{}", headers=headers, now=now)
