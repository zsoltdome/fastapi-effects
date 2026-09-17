"""Small receiver showing signature verification and stable-ID deduplication."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import timedelta

from fastapi import FastAPI, HTTPException, Request

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.webhooks.secrets import decode_public_secret
from fastapi_mergen.webhooks.signing import verify_webhook

app = FastAPI(title="FastAPI-Mergen webhook receiver")
_processed: dict[str, str] = {}
_lock = asyncio.Lock()
_DEFAULT_MAX_BODY_BYTES = 1024 * 1024
_MAX_CONFIGURED_BODY_BYTES = 16 * 1024 * 1024


@app.post("/hooks")
async def receive(
    request: Request,
) -> dict[str, object]:
    configured = os.getenv("WEBHOOK_SIGNING_SECRETS") or os.getenv("WEBHOOK_SIGNING_SECRET")
    if not configured:
        raise HTTPException(status_code=503, detail="Receiver secret is not configured.")
    configured_secrets = tuple(item.strip() for item in configured.split(",") if item.strip())
    if not configured_secrets:
        raise HTTPException(status_code=503, detail="Receiver secret is not configured.")
    try:
        secrets = tuple(decode_public_secret(secret) for secret in configured_secrets)
        maximum_body_bytes = _integer_setting(
            "WEBHOOK_MAX_BODY_BYTES",
            default=_DEFAULT_MAX_BODY_BYTES,
            minimum=1,
            maximum=_MAX_CONFIGURED_BODY_BYTES,
        )
        maximum_age = timedelta(
            seconds=_integer_setting(
                "WEBHOOK_MAX_AGE_SECONDS", default=300, minimum=0, maximum=86400
            )
        )
        maximum_future_skew = timedelta(
            seconds=_integer_setting(
                "WEBHOOK_MAX_FUTURE_SKEW_SECONDS",
                default=300,
                minimum=0,
                maximum=86400,
            )
        )
    except MergenConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Receiver configuration is invalid.") from exc
    headers = _security_headers(request)
    body = await _bounded_body(request, maximum=maximum_body_bytes)
    verified = any(
        verify_webhook(
            secret=secret,
            body=body,
            headers=headers,
            maximum_age=maximum_age,
            maximum_future_skew=maximum_future_skew,
        )
        for secret in secrets
    )
    if not verified:
        raise HTTPException(status_code=400, detail="Signature verification failed.")
    webhook_id = headers["webhook-id"]
    digest = hashlib.sha256(body).hexdigest()
    async with _lock:
        duplicate = webhook_id in _processed
        if duplicate and _processed[webhook_id] != digest:
            raise HTTPException(
                status_code=409, detail="Message identity conflicts with prior body."
            )
        if not duplicate:
            # Replace this set with a UNIQUE(message_id) insert in the receiver's
            # business transaction before applying the effect.
            _processed[webhook_id] = digest
    return {"accepted": True, "duplicate": duplicate, "message_id": webhook_id}


def _security_headers(request: Request) -> dict[str, str]:
    required = (b"webhook-id", b"webhook-timestamp", b"webhook-signature")
    result: dict[str, str] = {}
    for name in required:
        values = [value for key, value in request.scope.get("headers", ()) if key.lower() == name]
        if len(values) != 1:
            raise HTTPException(status_code=400, detail="Security headers must occur exactly once.")
        try:
            result[name.decode("ascii")] = values[0].decode("ascii")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Security headers must be ASCII.") from exc
    return result


async def _bounded_body(request: Request, *, maximum: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(chunk) > maximum - len(body):
            raise HTTPException(status_code=413, detail="Webhook body exceeds configured limit.")
        body.extend(chunk)
    return bytes(body)


def _integer_setting(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise MergenConfigurationError(f"{name} must be an integer.") from exc
    if value < minimum or value > maximum:
        raise MergenConfigurationError(f"{name} is outside the supported range.")
    return value
