"""Capability manifest used to select and certify conformance scenarios."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi_mergen.conformance.contract import (
    CONTRACT_VERSION,
    MANIFEST_SCHEMA_VERSION,
    Capability,
    Invariant,
    required_capabilities,
)
from fastapi_mergen.conformance.safety import JsonValue, reject_sensitive_keys, safe_json
from fastapi_mergen.errors import MergenConfigurationError, SchemaRevisionMismatch

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,127}$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    """Immutable declaration of the facets an implementation can exercise."""

    adapter_name: str
    adapter_version: str
    implementation: str
    capabilities: frozenset[Capability]
    invariants: frozenset[Invariant]
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.adapter_name, str) or not _NAME.fullmatch(self.adapter_name):
            raise MergenConfigurationError("Capability manifest adapter_name is invalid.")
        if not isinstance(self.adapter_version, str) or not _VERSION.fullmatch(
            self.adapter_version
        ):
            raise MergenConfigurationError("Capability manifest adapter_version is invalid.")
        if not isinstance(self.implementation, str) or not _NAME.fullmatch(self.implementation):
            raise MergenConfigurationError("Capability manifest implementation is invalid.")
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise SchemaRevisionMismatch(
                component="conformance-manifest",
                expected=MANIFEST_SCHEMA_VERSION,
                actual=self.schema_version,
            )
        if self.contract_version != CONTRACT_VERSION:
            raise MergenConfigurationError("Unsupported Boundary Contract version.")
        capabilities = frozenset(self.capabilities)
        invariants = frozenset(self.invariants)
        if any(not isinstance(item, Capability) for item in capabilities):
            raise MergenConfigurationError("Manifest contains an unknown capability.")
        if any(not isinstance(item, Invariant) for item in invariants):
            raise MergenConfigurationError("Manifest contains an unknown invariant.")
        for invariant in invariants:
            missing = required_capabilities(invariant) - capabilities
            if missing:
                names = ", ".join(sorted(item.value for item in missing))
                raise MergenConfigurationError(
                    f"Invariant {invariant.value} requires undeclared capabilities: {names}."
                )
        reject_sensitive_keys(self.metadata)
        normalized = safe_json(self.metadata)
        if not isinstance(normalized, dict):
            raise MergenConfigurationError("Manifest metadata must be a mapping.")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "invariants", invariants)
        object.__setattr__(self, "metadata", normalized)

    def as_dict(self) -> dict[str, JsonValue]:
        """Return the canonical manifest representation."""

        return {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "implementation": self.implementation,
            "capabilities": sorted(item.value for item in self.capabilities),
            "invariants": sorted(item.value for item in self.invariants),
            "metadata": self.metadata,
        }

    def canonical_bytes(self) -> bytes:
        """Serialize without insignificant whitespace or unstable key ordering."""

        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def digest(self) -> str:
        """Return the stable SHA-256 identity of the declaration."""

        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize a human- or machine-readable manifest."""

        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=indent,
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CapabilityManifest:
        """Parse a strict manifest mapping."""

        expected = {
            "schema_version",
            "contract_version",
            "adapter_name",
            "adapter_version",
            "implementation",
            "capabilities",
            "invariants",
            "metadata",
        }
        if set(value) != expected:
            raise MergenConfigurationError("Capability manifest fields are incomplete or unknown.")
        if (
            not isinstance(value["schema_version"], int)
            or isinstance(value["schema_version"], bool)
        ):
            raise MergenConfigurationError("Capability manifest schema_version is invalid.")
        for field_name in (
            "contract_version",
            "adapter_name",
            "adapter_version",
            "implementation",
        ):
            if not isinstance(value[field_name], str):
                raise MergenConfigurationError(
                    f"Capability manifest {field_name} is invalid."
                )
        if not isinstance(value["capabilities"], list) or not isinstance(
            value["invariants"], list
        ):
            raise MergenConfigurationError(
                "Capability manifest capabilities and invariants must be arrays."
            )
        if len(value["capabilities"]) != len(set(value["capabilities"])):
            raise MergenConfigurationError("Capability manifest repeats a capability.")
        if len(value["invariants"]) != len(set(value["invariants"])):
            raise MergenConfigurationError("Capability manifest repeats an invariant.")
        try:
            capabilities = frozenset(Capability(item) for item in value["capabilities"])
            invariants = frozenset(Invariant(item) for item in value["invariants"])
        except (TypeError, ValueError) as exc:
            raise MergenConfigurationError("Capability manifest enumeration is invalid.") from exc
        metadata = value["metadata"]
        if not isinstance(metadata, dict):
            raise MergenConfigurationError("Capability manifest metadata must be a mapping.")
        return cls(
            schema_version=value["schema_version"],
            contract_version=value["contract_version"],
            adapter_name=value["adapter_name"],
            adapter_version=value["adapter_version"],
            implementation=value["implementation"],
            capabilities=capabilities,
            invariants=invariants,
            metadata=metadata,
        )

    @classmethod
    def from_json(cls, payload: str | bytes) -> CapabilityManifest:
        """Parse strict JSON and reject duplicate object keys."""

        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise MergenConfigurationError("Capability manifest contains duplicate keys.")
                result[key] = item
            return result

        try:
            decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            value = json.loads(decoded, object_pairs_hook=reject_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MergenConfigurationError("Capability manifest is not valid UTF-8 JSON.") from exc
        if not isinstance(value, dict):
            raise MergenConfigurationError("Capability manifest root must be an object.")
        return cls.from_dict(value)
