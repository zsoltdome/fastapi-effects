"""Bounded stable identities used by persistence, retries, and replay."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi_mergen.errors import MergenConfigurationError

_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MAX_KEY_BYTES = 512


@dataclass(frozen=True, slots=True)
class DedupeIdentity:
    """Tenant-local caller identity for one immutable emitted event."""

    namespace: str
    key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, str) or not _NAMESPACE.fullmatch(self.namespace):
            raise MergenConfigurationError("Dedupe namespace is invalid.")
        if (
            not isinstance(self.key, str)
            or not self.key
            or self.key != self.key.strip()
            or _CONTROL.search(self.key) is not None
        ):
            raise MergenConfigurationError("Dedupe key is invalid.")
        try:
            length = len(self.key.encode("utf-8"))
        except UnicodeError as exc:
            raise MergenConfigurationError("Dedupe key is invalid.") from exc
        if length > _MAX_KEY_BYTES:
            raise MergenConfigurationError("Dedupe key is invalid.")

    @property
    def digest(self) -> bytes:
        value = f"{self.namespace}\0{self.key}".encode()
        return hashlib.sha256(value).digest()


class UUIDSource:
    """Default injectable UUID source; UUID ordering is not a contract."""

    def new_uuid(self) -> UUID:
        return uuid4()


__all__ = ["DedupeIdentity", "UUIDSource"]
