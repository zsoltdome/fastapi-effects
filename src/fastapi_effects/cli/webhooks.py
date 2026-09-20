"""Webhook endpoint policy diagnostics without DNS or network side effects."""

from __future__ import annotations

from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.webhooks.address_policy import parse_endpoint


def validate_endpoint(url: str, *, development: bool = False) -> int:
    try:
        target = parse_endpoint(
            url,
            production=not development,
            allowed_ports=frozenset({80, 443}) if development else frozenset({443}),
        )
    except FastAPIEffectsConfigurationError as exc:
        print(f"invalid endpoint: {exc}")
        return 2
    print(
        f"valid endpoint: scheme={target.scheme} host={target.hostname} "
        f"port={target.port} target={target.request_target}"
    )
    return 0


__all__ = ["validate_endpoint"]
