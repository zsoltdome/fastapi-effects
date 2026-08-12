from __future__ import annotations

import pytest

from fastapi_mergen.delegation.targets import canonical_target_path
from fastapi_mergen.errors import MergenConfigurationError


@pytest.mark.parametrize(
    "path",
    [
        "v1/pay",
        "//evil.example/pay",
        "/v1/../admin",
        "/v1/%2e%2e/admin",
        "/v1/%252e%252e/admin",
        "/v1/%2Fadmin",
        "/v1/%5cadmin",
        "/v1\\admin",
        "/v1/%zz",
        "/v1/pay?admin=true",
        "/v1/pay#fragment",
        "/v1//pay",
        "/v1/\x00pay",
    ],
)
def test_ambiguous_delegation_targets_fail_closed(path: str) -> None:
    with pytest.raises(MergenConfigurationError):
        canonical_target_path(path)


def test_unreserved_percent_encoding_has_one_canonical_form() -> None:
    assert canonical_target_path("/v1/invoices/%34%32/pay") == "/v1/invoices/42/pay"
