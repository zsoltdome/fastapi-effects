"""Small receiver showing signature verification and stable-ID deduplication."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request

from fastapi_mergen.webhooks.secrets import decode_public_secret
from fastapi_mergen.webhooks.signing import verify_webhook

app = FastAPI(title="FastAPI-Mergen webhook receiver")
_processed: set[str] = set()
_lock = asyncio.Lock()


@app.post("/hooks")
async def receive(
    request: Request,
    webhook_id: Annotated[str, Header(alias="webhook-id")],
    webhook_timestamp: Annotated[str, Header(alias="webhook-timestamp")],
    webhook_signature: Annotated[str, Header(alias="webhook-signature")],
) -> dict[str, object]:
    configured = os.getenv("WEBHOOK_SIGNING_SECRETS") or os.getenv("WEBHOOK_SIGNING_SECRET")
    if not configured:
        raise HTTPException(status_code=503, detail="Receiver secret is not configured.")
    configured_secrets = tuple(item.strip() for item in configured.split(",") if item.strip())
    if not configured_secrets:
        raise HTTPException(status_code=503, detail="Receiver secret is not configured.")
    body = await request.body()
    headers = {
        "webhook-id": webhook_id,
        "webhook-timestamp": webhook_timestamp,
        "webhook-signature": webhook_signature,
    }
    verified = any(
        verify_webhook(
            secret=decode_public_secret(secret),
            body=body,
            headers=headers,
        )
        for secret in configured_secrets
    )
    if not verified:
        raise HTTPException(status_code=400, detail="Signature verification failed.")
    async with _lock:
        duplicate = webhook_id in _processed
        if not duplicate:
            # Replace this set with a UNIQUE(message_id) insert in the receiver's
            # business transaction before applying the effect.
            _processed.add(webhook_id)
    return {"accepted": True, "duplicate": duplicate, "message_id": webhook_id}
