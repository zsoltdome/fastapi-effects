"""Standard Webhooks-compatible signing over exact request bytes."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from fastapi_mergen.errors import MergenConfigurationError

_MESSAGE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TIMESTAMP = re.compile(r"^[0-9]{1,16}$")
_SIGNATURE_LIMIT = 8
_SIGNATURE_HEADER_LIMIT = 4096
_DEFAULT_MAXIMUM_AGE = timedelta(minutes=5)
_DEFAULT_MAXIMUM_FUTURE_SKEW = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class SignedWebhookHeaders:
    values: Mapping[str, str]
    signature_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


def sign_webhook(
    *,
    message_id: str,
    timestamp: datetime,
    body: bytes,
    secrets: Iterable[bytes],
) -> SignedWebhookHeaders:
    if not isinstance(message_id, str) or not _MESSAGE_ID.fullmatch(message_id):
        raise MergenConfigurationError("Webhook message ID is invalid.")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise MergenConfigurationError("Webhook signing timestamp must be timezone-aware.")
    if not isinstance(body, bytes):
        raise MergenConfigurationError("Webhook body must be bytes.")
    timestamp_text = str(int(timestamp.timestamp()))
    signed_content = message_id.encode() + b"." + timestamp_text.encode() + b"." + body
    signatures: list[str] = []
    for secret in secrets:
        if not isinstance(secret, bytes) or len(secret) < 16:
            raise MergenConfigurationError("Webhook signing key is invalid.")
        digest = hmac.new(secret, signed_content, hashlib.sha256).digest()
        signatures.append("v1," + base64.b64encode(digest).decode("ascii"))
    if not signatures:
        raise MergenConfigurationError("Webhook signing requires an eligible key.")
    return SignedWebhookHeaders(
        values={
            "content-type": "application/json",
            "webhook-id": message_id,
            "webhook-signature": " ".join(signatures),
            "webhook-timestamp": timestamp_text,
        },
        signature_count=len(signatures),
    )


def verify_webhook(
    *,
    secret: bytes,
    body: bytes,
    headers: Mapping[str, str],
    now: datetime | None = None,
    maximum_age: timedelta = _DEFAULT_MAXIMUM_AGE,
    maximum_future_skew: timedelta = _DEFAULT_MAXIMUM_FUTURE_SKEW,
) -> bool:
    """Verify exact bytes plus a bounded Standard Webhooks attempt timestamp."""

    if not isinstance(secret, bytes) or len(secret) < 16:
        raise MergenConfigurationError("Webhook verification key is invalid.")
    if not isinstance(body, bytes):
        raise MergenConfigurationError("Webhook verification body must be bytes.")
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise MergenConfigurationError("Webhook verification time must be timezone-aware.")
    for name, tolerance in (
        ("maximum_age", maximum_age),
        ("maximum_future_skew", maximum_future_skew),
    ):
        if (
            not isinstance(tolerance, timedelta)
            or tolerance < timedelta(0)
            or tolerance > timedelta(days=1)
        ):
            raise MergenConfigurationError(f"Webhook {name} is invalid.")

    normalized: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in normalized and lowered in {
            "webhook-id",
            "webhook-signature",
            "webhook-timestamp",
        }:
            return False
        normalized[lowered] = value
    message_id = normalized.get("webhook-id")
    timestamp = normalized.get("webhook-timestamp")
    supplied = normalized.get("webhook-signature")
    if (
        message_id is None
        or _MESSAGE_ID.fullmatch(message_id) is None
        or timestamp is None
        or _TIMESTAMP.fullmatch(timestamp) is None
        or supplied is None
        or not supplied
        or len(supplied) > _SIGNATURE_HEADER_LIMIT
    ):
        return False
    timestamp_value = int(timestamp)
    current_value = int(current.timestamp())
    age_seconds = current_value - timestamp_value
    if age_seconds > int(maximum_age.total_seconds()):
        return False
    if -age_seconds > int(maximum_future_skew.total_seconds()):
        return False
    content = message_id.encode() + b"." + timestamp.encode() + b"." + body
    expected = hmac.new(secret, content, hashlib.sha256).digest()
    candidates = supplied.split()
    if not candidates or len(candidates) > _SIGNATURE_LIMIT:
        return False
    for candidate in candidates:
        version, separator, encoded = candidate.partition(",")
        if version != "v1" or not separator:
            continue
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            continue
        if len(decoded) == hashlib.sha256().digest_size and hmac.compare_digest(expected, decoded):
            return True
    return False


__all__ = ["SignedWebhookHeaders", "sign_webhook", "verify_webhook"]
