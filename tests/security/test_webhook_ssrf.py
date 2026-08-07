from __future__ import annotations

import pytest

from fastapi_mergen.errors import MergenConfigurationError, PermanentDeliveryError
from fastapi_mergen.webhooks.address_policy import parse_endpoint, validate_public_addresses

pytestmark = pytest.mark.security


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hooks",
        "https://user:password@example.com/hooks",
        "https://example.com/hooks#fragment",
        "https://example.com:8443/hooks",
        "https://example.com/line\nbreak",
        "https://[::1",
    ],
)
def test_hostile_endpoint_syntax_fails_closed(url: str) -> None:
    with pytest.raises(MergenConfigurationError):
        parse_endpoint(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "100.64.0.1",
        "169.254.169.254",
        "192.0.2.1",
        "198.18.0.1",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "::ffff:127.0.0.1",
        "2001:db8::1",
    ],
)
def test_forbidden_address_classes_fail_closed(address: str) -> None:
    with pytest.raises(PermanentDeliveryError):
        validate_public_addresses([address])


def test_mixed_dns_answer_fails_closed() -> None:
    with pytest.raises(PermanentDeliveryError):
        validate_public_addresses(["93.184.216.34", "127.0.0.1"])


def test_public_answer_and_idna_are_normalized() -> None:
    endpoint = parse_endpoint("https://BÜCHER.example/hooks?q=1")
    assert endpoint.hostname == "xn--bcher-kva.example"
    assert endpoint.request_target == "/hooks?q=1"
    assert validate_public_addresses(["93.184.216.34"]) == ("93.184.216.34",)
