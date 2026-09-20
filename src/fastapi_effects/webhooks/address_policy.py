"""Fail-closed webhook URL and resolved-address policy."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi_effects.errors import FastAPIEffectsConfigurationError, PermanentDeliveryError

_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_PATH_SAFE = "/:@-._~!$&'()*+,;=%"
_QUERY_SAFE = "/?:@-._~!$&'()*+,;=%"


@dataclass(frozen=True, slots=True)
class EndpointTarget:
    """Normalized authority retained through DNS, TLS, and HTTP."""

    url: str
    scheme: str
    hostname: str
    port: int
    authority: str
    request_target: str


def parse_endpoint(
    value: str,
    *,
    production: bool = True,
    allowed_ports: frozenset[int] = frozenset({443}),
) -> EndpointTarget:
    """Parse a webhook URL without performing DNS or accepting ambiguous authority."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or _CONTROL_OR_SPACE.search(value) is not None
    ):
        raise FastAPIEffectsConfigurationError("Webhook endpoint URL is invalid.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise FastAPIEffectsConfigurationError("Webhook endpoint authority is invalid.") from exc
    allowed_schemes = {"https"} if production else {"http", "https"}
    if parsed.scheme.lower() not in allowed_schemes:
        raise FastAPIEffectsConfigurationError("Webhook endpoint scheme is not allowed.")
    if (
        not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.hostname is None
    ):
        raise FastAPIEffectsConfigurationError("Webhook endpoint authority is invalid.")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise FastAPIEffectsConfigurationError("Webhook endpoint hostname is invalid.") from exc
    if not hostname or len(hostname) > 253:
        raise FastAPIEffectsConfigurationError("Webhook endpoint hostname is invalid.")
    effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if effective_port not in allowed_ports:
        raise FastAPIEffectsConfigurationError("Webhook endpoint port is not allowed.")
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    authority = (
        display_host if effective_port == default_port else f"{display_host}:{effective_port}"
    )
    if _INVALID_PERCENT_ESCAPE.search(parsed.path) or _INVALID_PERCENT_ESCAPE.search(parsed.query):
        raise FastAPIEffectsConfigurationError(
            "Webhook endpoint URL contains an invalid percent escape."
        )
    # HTTP/1.1 request targets are URI bytes, not raw IRIs. Encode Unicode once
    # while retaining existing percent escapes and all RFC 3986 reserved syntax.
    try:
        path = quote(parsed.path or "/", safe=_PATH_SAFE, encoding="utf-8", errors="strict")
        query = quote(parsed.query, safe=_QUERY_SAFE, encoding="utf-8", errors="strict")
    except UnicodeError as exc:
        raise FastAPIEffectsConfigurationError(
            "Webhook endpoint URL contains invalid Unicode."
        ) from exc
    request_target = path + (f"?{query}" if query else "")
    normalized = urlunsplit((parsed.scheme.lower(), authority, path, query, ""))
    return EndpointTarget(
        url=normalized,
        scheme=parsed.scheme.lower(),
        hostname=hostname,
        port=effective_port,
        authority=authority,
        request_target=request_target,
    )


def validate_public_addresses(addresses: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Require a nonempty answer set consisting only of global unicast addresses."""
    if not addresses or len(addresses) > 32:
        raise PermanentDeliveryError(
            code="webhook.dns_policy",
            summary="Endpoint DNS returned no acceptable bounded answer set.",
        )
    normalized: list[str] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise PermanentDeliveryError(
                code="webhook.address_invalid",
                summary="Endpoint DNS returned an invalid address.",
            ) from exc
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None:
            raise PermanentDeliveryError(
                code="webhook.address_forbidden",
                summary="Endpoint DNS returned an IPv4-mapped IPv6 address.",
            )
        if (
            not address.is_global
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or address.is_loopback
            or address.is_link_local
            or address.is_private
        ):
            raise PermanentDeliveryError(
                code="webhook.address_forbidden",
                summary="Endpoint DNS returned a forbidden non-global address.",
            )
        canonical = address.compressed
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


__all__ = ["EndpointTarget", "parse_endpoint", "validate_public_addresses"]
