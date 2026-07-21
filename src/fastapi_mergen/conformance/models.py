"""Immutable conformance result and report values."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, NoReturn
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
_MAX_REPORT_BYTES = 8 * 1024 * 1024
_MAX_RESULTS = 2048


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
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise MergenConfigurationError("Conformance duration_ms must be non-negative.")
        if not isinstance(self.summary, str):
            raise MergenConfigurationError("Conformance summary must be text.")
        summary = clean_text(self.summary, maximum=512)
        if not summary:
            raise MergenConfigurationError("Conformance summary must not be empty.")
        object.__setattr__(self, "summary", summary)
        normalized = safe_json(self.evidence)
        if not isinstance(normalized, dict):
            raise MergenConfigurationError("Conformance evidence must be a mapping.")
        object.__setattr__(self, "evidence", normalized)
        if self.remediation is not None:
            if not isinstance(self.remediation, str):
                raise MergenConfigurationError("Conformance remediation must be text.")
            object.__setattr__(
                self,
                "remediation",
                clean_text(self.remediation, maximum=1024),
            )
        if self.exception_type is not None:
            if not isinstance(self.exception_type, str):
                raise MergenConfigurationError("Conformance exception_type must be text.")
            object.__setattr__(
                self,
                "exception_type",
                clean_text(self.exception_type, maximum=256),
            )

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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CheckResult:
        """Parse one strict, machine-readable check result."""

        if not isinstance(value, dict):
            raise MergenConfigurationError("Conformance check must be an object.")
        expected = {
            "check_id",
            "invariant",
            "status",
            "severity",
            "summary",
            "duration_ms",
            "evidence",
            "remediation",
            "exception_type",
        }
        if set(value) != expected:
            raise MergenConfigurationError("Conformance check fields are incomplete or unknown.")
        try:
            invariant = Invariant(value["invariant"])
            status = CheckStatus(value["status"])
            severity = Severity(value["severity"])
        except (TypeError, ValueError) as exc:
            raise MergenConfigurationError("Conformance check enumeration is invalid.") from exc
        evidence = value["evidence"]
        if not isinstance(evidence, dict):
            raise MergenConfigurationError("Conformance check evidence must be an object.")
        return cls(
            check_id=value["check_id"],
            invariant=invariant,
            status=status,
            severity=severity,
            summary=value["summary"],
            duration_ms=value["duration_ms"],
            evidence=evidence,
            remediation=value["remediation"],
            exception_type=value["exception_type"],
        )


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
        if len(self.results) > _MAX_RESULTS:
            raise MergenConfigurationError("Conformance report contains too many results.")
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

        if not self.results:
            return CheckStatus.ERROR
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

    def canonical_bytes(self) -> bytes:
        """Return deterministic bytes used for report artifact identity."""

        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def digest(self) -> str:
        """Return the SHA-256 identity of this exact report."""

        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ConformanceReport:
        """Parse a rendered report and verify every derived field."""

        if not isinstance(value, dict):
            raise MergenConfigurationError("Conformance report must be an object.")
        expected = {
            "schema_version",
            "contract_version",
            "run_id",
            "profile",
            "manifest_digest",
            "started_at",
            "finished_at",
            "status",
            "certified",
            "counts",
            "environment",
            "results",
        }
        supplied_digest = value.get("report_digest")
        if supplied_digest is not None:
            if not isinstance(supplied_digest, str) or not _DIGEST.fullmatch(
                supplied_digest
            ):
                raise MergenConfigurationError(
                    "Conformance report digest must be a SHA-256 hex digest."
                )
            value = dict(value)
            del value["report_digest"]
        if set(value) != expected:
            raise MergenConfigurationError("Conformance report fields are incomplete or unknown.")
        if not isinstance(value["results"], list):
            raise MergenConfigurationError("Conformance report results must be an array.")
        if not isinstance(value["environment"], dict):
            raise MergenConfigurationError("Conformance report environment must be an object.")
        if any(not isinstance(item, dict) for item in value["results"]):
            raise MergenConfigurationError(
                "Conformance report results must contain objects."
            )
        try:
            profile = CertificationProfile(value["profile"])
            run_id = UUID(value["run_id"])
            started_at = datetime.fromisoformat(value["started_at"])
            finished_at = datetime.fromisoformat(value["finished_at"])
            results = tuple(CheckResult.from_dict(item) for item in value["results"])
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            raise MergenConfigurationError("Conformance report value is invalid.") from exc
        report = cls(
            schema_version=value["schema_version"],
            contract_version=value["contract_version"],
            run_id=run_id,
            profile=profile,
            manifest_digest=value["manifest_digest"],
            started_at=started_at,
            finished_at=finished_at,
            environment=value["environment"],
            results=results,
        )
        if value["status"] != report.status.value:
            raise MergenConfigurationError("Conformance report status is inconsistent.")
        if value["certified"] is not report.certified:
            raise MergenConfigurationError("Conformance report certification is inconsistent.")
        if value["counts"] != report.counts():
            raise MergenConfigurationError("Conformance report counts are inconsistent.")
        if supplied_digest is not None and supplied_digest != report.digest:
            raise MergenConfigurationError("Conformance report digest is inconsistent.")
        return report

    @classmethod
    def from_json(cls, payload: str | bytes) -> ConformanceReport:
        """Parse strict, bounded UTF-8 JSON and reject duplicate object keys."""

        if not isinstance(payload, str | bytes):
            raise MergenConfigurationError("Conformance report JSON must be text or bytes.")
        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        if len(encoded) > _MAX_REPORT_BYTES:
            raise MergenConfigurationError("Conformance report JSON exceeds the size limit.")

        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise MergenConfigurationError(
                        "Conformance report contains duplicate object keys."
                    )
                result[key] = item
            return result


        def reject_constant(_value: str) -> NoReturn:
            raise MergenConfigurationError("Conformance report contains a non-finite number.")

        try:
            decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            value = json.loads(
                decoded,
                object_pairs_hook=reject_duplicates,
                parse_constant=reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MergenConfigurationError(
                "Conformance report is not valid UTF-8 JSON."
            ) from exc
        if not isinstance(value, dict):
            raise MergenConfigurationError("Conformance report root must be an object.")
        return cls.from_dict(value)
