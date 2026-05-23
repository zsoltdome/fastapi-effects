"""Optional webhook integration boundary reserved for Milestone 3."""

from fastapi_mergen._optional import require_modules

require_modules(
    feature="Webhook support",
    extra="webhooks",
    modules=("cryptography", "httpx", "standardwebhooks"),
)
