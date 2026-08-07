"""Standard Webhooks-compatible signing over exact request bytes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from fastapi_mergen.errors import MergenConfigurationError

_MESSAGE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


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
) -> bool:
    """Small receiver helper compatible with Standard Webhooks header semantics."""
    normalized = {key.lower(): value for key, value in headers.items()}
    message_id = normalized.get("webhook-id")
    timestamp = normalized.get("webhook-timestamp")
    supplied = normalized.get("webhook-signature")
    if message_id is None or timestamp is None or supplied is None or not timestamp.isdigit():
        return False
    content = message_id.encode() + b"." + timestamp.encode() + b"." + body
    expected = hmac.new(secret, content, hashlib.sha256).digest()
    for candidate in supplied.split():
        version, separator, encoded = candidate.partition(",")
        if version != "v1" or not separator:
            continue
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except ValueError:
            continue
        if hmac.compare_digest(expected, decoded):
            return True
    return False


__all__ = ["SignedWebhookHeaders", "sign_webhook", "verify_webhook"]
