"""Authorization policy values for the public API spike."""

from __future__ import annotations

from enum import StrEnum
from fastapi_mergen.errors import MergenConfigurationError


class AuthorizationMode(StrEnum):
    """Authority source used for a delivery attempt."""

    SNAPSHOT = "snapshot"
    REVALIDATE = "revalidate"
    SERVICE_POLICY = "service_policy"

    @classmethod
    def parse(cls, value: AuthorizationMode | str) -> AuthorizationMode:
        """Parse a public string without accepting undocumented aliases."""
        try:
            return cls(value)
        except (TypeError, ValueError) as exc:
            raise MergenConfigurationError(
                f"Unsupported authorization mode: {value!r}."
            ) from exc
