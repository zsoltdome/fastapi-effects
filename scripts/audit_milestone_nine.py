"""Static completeness checks for the webhook MDP implementation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "src/fastapi_effects/webhooks/models.py",
    "src/fastapi_effects/webhooks/secrets.py",
    "src/fastapi_effects/webhooks/subscriptions.py",
    "src/fastapi_effects/webhooks/serializer.py",
    "src/fastapi_effects/webhooks/signing.py",
    "src/fastapi_effects/webhooks/address_policy.py",
    "src/fastapi_effects/webhooks/http11.py",
    "src/fastapi_effects/webhooks/transport.py",
    "src/fastapi_effects/webhooks/sink.py",
    "src/fastapi_effects/webhooks/operations.py",
    "src/fastapi_effects/postgres/migrations/versions/0002_webhooks.py",
    "src/fastapi_effects/testing/webhook_driver.py",
    "tests/conformance/test_real_webhooks.py",
    "tests/security/test_webhook_redirects.py",
    "tests/chaos/test_webhook_crash_matrix.py",
    "examples/webhook_receiver/app.py",
)


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    transport = (ROOT / "src/fastapi_effects/webhooks/transport.py").read_text()
    certification = (ROOT / "src/fastapi_effects/testing/webhook_driver.py").read_text()
    forbidden = [
        name for name in ("httpx.AsyncClient", "follow_redirects=True") if name in transport
    ]
    missing_boundaries = [
        item
        for item in ("WebhookDeliverySink", "ExplicitIPTransport", "asyncio.start_server")
        if item not in certification
    ]
    if missing or forbidden or missing_boundaries:
        for item in missing:
            print(f"missing: {item}")
        for item in forbidden:
            print(f"unsafe transport primitive: {item}")
        for item in missing_boundaries:
            print(f"missing webhook certification boundary: {item}")
        return 1
    print("Milestone 9 webhook implementation audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
