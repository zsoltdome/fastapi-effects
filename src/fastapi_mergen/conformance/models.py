"""Immutable conformance result and report values."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from fastapi_mergen.conformance.contract import (
    CONTRACT_VERSION,
    REPORT_SCHEMA_VERSION,
    CertificationProfile,
    Invariant,
    profile_invariants,
)
from fastapi_mergen.conformance.safety import JsonValue, clean_text, safe_json
from fastapi_mergen.errors import MergenConfigurationError

_CHECK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,159}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


class CheckStatus(StrEnum):
    """Terminal status for one deterministic conformance check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class Severity(StrEnum):
    """Security and correctness importance assigned to a check."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One bounded, serializable conformance observation."""

    check_id: str
    invariant: Invariant
    status: CheckStatus
    severity: Severity
    summary: str
    duration_ms: int
    evidence: dict[str, JsonValue] = field(default_factory=dict)
    remediation: str | None = None
    exception_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not _CHECK_ID.fullmatch(self.check_id):
            raise MergenConfigurationError("Conformance check_id is invalid.")
        if not isinstance(self.invariant, Invariant):
            raise MergenConfigurationError("Conformance invariant is invalid.")
        if not isinstance(self.status, CheckStatus):
            raise MergenConfigurationError("Conformance status is invalid.")
        if not isinstance(self.severity, Severity):
            raise MergenConfigurationError("Conformance severity is invalid.")
        if not isinstance(self.duration_ms, int) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise MergenConfigurationError("Conformance duration_ms must be non-negative.")
        summary = clean_text(self.summary, maximum=512)
        if not summary:
            raise MergenConfigurationError("Conformance summary must not be empty.")
        object.__setattr__(self, "summary", summary)
        normalized = safe_json(self.evidence)
        if not isinstance(normalized, dict):
            raise MergenConfigurationError("Conformance evidence must be a mapping.")
        object.__setattr__(self, "evidence", normalized)
        if self.remediation is not None:
            object.__setattr__(self, "remediation", clean_text(self.remediation, maximum=1024))
        if self.exception_type is not None:
            object.__setattr__(self, "exception_type", clean_text(self.exception_type, maximum=256))

    def as_dict(self) -> dict[str, JsonValue]:
        """Return a stable public representation."""

        return {
            "check_id": self.check_id,
            "invariant": self.invariant.value,
            "status": self.status.value,
            "severity": self.severity.value,
            "summary": self.summary,
            "duration_ms": self.duration_ms,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "exception_type": self.exception_type,
        }


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """Machine-readable result of one profile run against one manifest."""

    profile: CertificationProfile
    manifest_digest: str
    results: tuple[CheckResult, ...]
    started_at: datetime
    finished_at: datetime
    run_id: UUID = field(default_factory=uuid4)
    contract_version: str = CONTRACT_VERSION
    schema_version: int = REPORT_SCHEMA_VERSION
    environment: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.profile, CertificationProfile):
            raise MergenConfigurationError("Conformance profile is invalid.")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != REPORT_SCHEMA_VERSION
        ):
            raise MergenConfigurationError("Conformance report schema version is invalid.")
        if self.contract_version != CONTRACT_VERSION:
            raise MergenConfigurationError("Conformance report contract version is invalid.")
        if not isinstance(self.manifest_digest, str) or not _DIGEST.fullmatch(
            self.manifest_digest
        ):
            raise MergenConfigurationError("Manifest digest must be a SHA-256 hex digest.")
        if not isinstance(self.run_id, UUID):
            raise MergenConfigurationError("Conformance run_id must be a UUID.")
        for name, value in (("started_at", self.started_at), ("finished_at", self.finished_at)):
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise MergenConfigurationError(f"Conformance {name} must be timezone-aware.")
        if self.finished_at < self.started_at:
            raise MergenConfigurationError("Conformance finished_at precedes started_at.")
        if not isinstance(self.results, tuple) or any(
            not isinstance(result, CheckResult) for result in self.results
        ):
            raise MergenConfigurationError("Conformance results must be CheckResult values.")
        check_ids = tuple(result.check_id for result in self.results)
        if len(check_ids) != len(set(check_ids)):
            raise MergenConfigurationError("Conformance report repeats a check_id.")
        normalized = safe_json(self.environment)
        if not isinstance(normalized, dict):
            raise MergenConfigurationError("Conformance environment must be a mapping.")
        object.__setattr__(self, "environment", normalized)

    @property
    def status(self) -> CheckStatus:
        """Return fail-closed aggregate status."""

        statuses = {result.status for result in self.results}
        if CheckStatus.ERROR in statuses:
            return CheckStatus.ERROR
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if self.results and statuses == {CheckStatus.SKIP}:
            return CheckStatus.SKIP
        return CheckStatus.PASS

    @property
    def certified(self) -> bool:
        """Return whether every selected invariant has passing, complete evidence."""

        required = profile_invariants(self.profile)
        passed = {
            result.invariant
            for result in self.results
            if result.status is CheckStatus.PASS
        }
        return required.issubset(passed) and bool(self.results) and all(
            result.status is CheckStatus.PASS for result in self.results
        )

    def counts(self) -> dict[str, int]:
        """Count results by status."""

        return {
            status.value: sum(result.status is status for result in self.results)
            for status in CheckStatus
        }

    def as_dict(self) -> dict[str, JsonValue]:
        """Return the versioned report representation."""

        return {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "run_id": str(self.run_id),
            "profile": self.profile.value,
            "manifest_digest": self.manifest_digest,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "finished_at": self.finished_at.astimezone(timezone.utc).isoformat(),
            "status": self.status.value,
            "certified": self.certified,
            "counts": self.counts(),
            "environment": self.environment,
            "results": [result.as_dict() for result in self.results],
        }
