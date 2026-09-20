"""Executable FastAPIEffects Boundary Contract conformance kit.

The conformance package is intentionally independent from a concrete database,
queue, webhook, or MCP implementation.  Implementations expose one or more
facet protocols and the runner executes deterministic boundary scenarios.
"""

from fastapi_effects.conformance.certification import (
    CertificationDecision,
    decide,
    verify_evidence,
)
from fastapi_effects.conformance.contract import (
    CONTRACT_VERSION,
    Capability,
    CertificationProfile,
    Invariant,
)
from fastapi_effects.conformance.manifest import CapabilityManifest
from fastapi_effects.conformance.models import (
    CheckResult,
    CheckStatus,
    ConformanceReport,
    Severity,
)
from fastapi_effects.conformance.reporters import ReportFormat, render_report, report_digest
from fastapi_effects.conformance.runner import ConformanceRunner, RunnerConfiguration

__all__ = [
    "CONTRACT_VERSION",
    "Capability",
    "CapabilityManifest",
    "CertificationDecision",
    "CertificationProfile",
    "CheckResult",
    "CheckStatus",
    "ConformanceReport",
    "ConformanceRunner",
    "Invariant",
    "ReportFormat",
    "RunnerConfiguration",
    "Severity",
    "decide",
    "render_report",
    "report_digest",
    "verify_evidence",
]
