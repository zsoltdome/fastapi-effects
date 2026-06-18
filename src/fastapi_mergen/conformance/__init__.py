"""Executable Mergen Boundary Contract conformance kit.

The conformance package is intentionally independent from a concrete database,
queue, webhook, or MCP implementation.  Implementations expose one or more
facet protocols and the runner executes deterministic boundary scenarios.
"""

from fastapi_mergen.conformance.contract import (
    CONTRACT_VERSION,
    Capability,
    CertificationProfile,
    Invariant,
)
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.models import (
    CheckResult,
    CheckStatus,
    ConformanceReport,
    Severity,
)

__all__ = [
    "CONTRACT_VERSION",
    "Capability",
    "CapabilityManifest",
    "CertificationProfile",
    "CheckResult",
    "CheckStatus",
    "ConformanceReport",
    "Invariant",
    "Severity",
]
