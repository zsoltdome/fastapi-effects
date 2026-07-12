from __future__ import annotations

from fastapi_mergen.conformance.safety import (
    reject_sensitive_keys,
    safe_json,
    scan_for_secret_values,
)
from fastapi_mergen.errors import MergenConfigurationError
import pytest


def test_nested_sensitive_fields_are_redacted() -> None:
    normalized = safe_json(
        {
            "nested": {
                "authorization": "Bearer secret",
                "cookie": "session=secret",
                "key_id": "public-key-id",
            }
        }
    )
    assert normalized == {
        "nested": {
            "authorization": "<redacted>",
            "cookie": "<redacted>",
            "key_id": "public-key-id",
        }
    }


def test_manifest_metadata_rejects_nested_sensitive_field() -> None:
    with pytest.raises(MergenConfigurationError):
        reject_sensitive_keys({"runtime": {"private_key": "secret"}})


def test_secret_canary_scan_uses_normalized_evidence() -> None:
    assert scan_for_secret_values({"diagnostic": "canary-value"}, ("canary-value",)) == (
        "canary-value",
    )
