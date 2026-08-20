"""Static completeness checks for the webhook MDP implementation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "src/fastapi_mergen/webhooks/models.py",
    "src/fastapi_mergen/webhooks/secrets.py",
    "src/fastapi_mergen/webhooks/subscriptions.py",
    "src/fastapi_mergen/webhooks/serializer.py",
    "src/fastapi_mergen/webhooks/signing.py",
    "src/fastapi_mergen/webhooks/address_policy.py",
    "src/fastapi_mergen/webhooks/http11.py",
    "src/fastapi_mergen/webhooks/transport.py",
    "src/fastapi_mergen/webhooks/sink.py",
    "src/fastapi_mergen/webhooks/operations.py",
    "src/fastapi_mergen/postgres/migrations/versions/0002_webhooks.py",
    "tests/conformance/test_real_webhooks.py",
    "tests/chaos/test_webhook_crash_matrix.py",
    "examples/webhook_receiver/app.py",
)


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    transport = (ROOT / "src/fastapi_mergen/webhooks/transport.py").read_text()
    forbidden = [
        name for name in ("httpx.AsyncClient", "follow_redirects=True") if name in transport
    ]
    if missing or forbidden:
        for item in missing:
            print(f"missing: {item}")
        for item in forbidden:
            print(f"unsafe transport primitive: {item}")
        return 1
    print("Milestone 9 webhook implementation audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
