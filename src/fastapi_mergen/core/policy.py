"""Authorization policy values for the public API spike."""

from __future__ import annotations

from enum import StrEnum


class AuthorizationMode(StrEnum):
    """Authority source used for a delivery attempt."""

    SNAPSHOT = "snapshot"
    REVALIDATE = "revalidate"
    SERVICE_POLICY = "service_policy"
