"""Optional OpenTelemetry integration boundary."""

from fastapi_mergen._optional import require_modules

require_modules(
    feature="OpenTelemetry support",
    extra="otel",
    modules=("opentelemetry", "opentelemetry.sdk"),
)
