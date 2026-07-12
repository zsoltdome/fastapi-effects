"""Fail-closed asynchronous conformance runner."""

from __future__ import annotations

import asyncio
import math
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi_mergen.conformance.contract import (
    CertificationProfile,
    Invariant,
    profile_invariants,
    required_capabilities,
)
from fastapi_mergen.conformance.models import (
    CheckResult,
    CheckStatus,
    ConformanceReport,
    Severity,
)
from fastapi_mergen.conformance.protocols import BoundaryDriver
from fastapi_mergen.conformance.safety import scan_for_secret_values
from fastapi_mergen.conformance.scenarios import SCENARIOS, Scenario
from fastapi_mergen.errors import MergenConfigurationError


@dataclass(frozen=True, slots=True)
class RunnerConfiguration:
    """Deterministic limits and selection for one conformance run."""

    profile: CertificationProfile = CertificationProfile.CORE
    check_timeout_seconds: float | None = None
    fail_fast: bool = False
    secret_canaries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.profile, CertificationProfile):
            raise MergenConfigurationError("Runner profile is invalid.")
        if self.check_timeout_seconds is not None and (
            not isinstance(self.check_timeout_seconds, int | float)
            or isinstance(self.check_timeout_seconds, bool)
            or not math.isfinite(self.check_timeout_seconds)
            or self.check_timeout_seconds <= 0
            or self.check_timeout_seconds > 300
        ):
            raise MergenConfigurationError("Runner check timeout must be within 0 and 300 seconds.")
        if not isinstance(self.fail_fast, bool):
            raise MergenConfigurationError("Runner fail_fast must be a boolean.")
        if not isinstance(self.secret_canaries, tuple):
            raise MergenConfigurationError("Runner secret canaries must be a tuple.")
        if len(self.secret_canaries) > 32:
            raise MergenConfigurationError("Runner accepts at most 32 secret canaries.")
        for canary in self.secret_canaries:
            if not isinstance(canary, str) or not canary or len(canary) > 4096:
                raise MergenConfigurationError("Runner secret canary is invalid.")


class ConformanceRunner:
    """Execute profile scenarios and produce bounded, machine-readable evidence."""

    def __init__(self, configuration: RunnerConfiguration | None = None) -> None:
        self.configuration = configuration or RunnerConfiguration()

    async def run(self, driver: BoundaryDriver) -> ConformanceReport:
        """Run selected checks; errors and unsupported facets fail certification."""

        if not isinstance(driver, BoundaryDriver):
            raise MergenConfigurationError(
                "Conformance driver does not implement lifecycle methods."
            )
        try:
            manifest = driver.manifest
        except Exception as exc:  # noqa: BLE001 - never expose adapter exception text
            await self._close_after_manifest_failure(driver)
            raise MergenConfigurationError(
                "Conformance driver manifest could not be read."
            ) from exc

        selected = profile_invariants(self.configuration.profile)
        started_at = datetime.now(timezone.utc)
        results: list[CheckResult] = []
        scenarios = tuple(
            scenario for scenario in SCENARIOS if scenario.invariant in selected
        )
        declared = manifest.invariants

        try:
            for invariant in sorted(selected, key=lambda item: item.value):
                if invariant in declared:
                    continue
                results.append(
                    CheckResult(
                        check_id=f"profile.{invariant.value.lower()}.unsupported",
                        invariant=invariant,
                        status=CheckStatus.SKIP,
                        severity=Severity.CRITICAL,
                        summary=(
                            "Implementation does not declare this required profile "
                            "invariant."
                        ),
                        duration_ms=0,
                        evidence={
                            "required_capabilities": sorted(
                                capability.value
                                for capability in required_capabilities(invariant)
                            )
                        },
                        remediation=(
                            "Declare and implement every invariant required by the "
                            "selected profile."
                        ),
                    )
                )
                if self.configuration.fail_fast:
                    break

            if not (self.configuration.fail_fast and results):
                for scenario in scenarios:
                    if scenario.invariant not in declared:
                        continue
                    if (
                        scenario.capability is not None
                        and scenario.capability not in manifest.capabilities
                    ):
                        results.append(
                            self._skip_for_capability(
                                scenario,
                                scenario.capability.value,
                            )
                        )
                        if self.configuration.fail_fast:
                            break
                        continue
                    result = await self._execute(driver, scenario)
                    results.append(result)
                    if (
                        self.configuration.fail_fast
                        and result.status is not CheckStatus.PASS
                    ):
                        break
        finally:
            cleanup = await self._cleanup_result(driver)
            if cleanup is not None:
                results.append(cleanup)

        finished_at = datetime.now(timezone.utc)
        return ConformanceReport(
            profile=self.configuration.profile,
            manifest_digest=manifest.digest,
            results=tuple(results),
            started_at=started_at,
            finished_at=finished_at,
            environment={
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "platform": sys.platform,
            },
        )

    @staticmethod
    async def _close_after_manifest_failure(driver: BoundaryDriver) -> None:
        try:
            await driver.close()
        except Exception:  # noqa: BLE001 - preserve the manifest failure
            pass

    @staticmethod
    async def _cleanup_result(driver: BoundaryDriver) -> CheckResult | None:
        try:
            await driver.close()
        except Exception as exc:  # noqa: BLE001 - report bounded type, never message
            return CheckResult(
                check_id="runner.cleanup",
                invariant=Invariant.CONTEXT_CLEANUP,
                status=CheckStatus.ERROR,
                severity=Severity.CRITICAL,
                summary="Driver cleanup raised an exception.",
                duration_ms=0,
                evidence={},
                remediation=(
                    "Make driver cleanup idempotent, bounded, and exception-safe."
                ),
                exception_type=f"{type(exc).__module__}.{type(exc).__qualname__}",
            )
        return None

    async def _execute(self, driver: BoundaryDriver, scenario: Scenario) -> CheckResult:
        started = time.monotonic_ns()
        timeout = self.configuration.check_timeout_seconds or scenario.timeout_seconds
        try:
            await asyncio.wait_for(driver.reset(), timeout=timeout)
            observation = await asyncio.wait_for(scenario.execute(driver), timeout=timeout)
            leaked = scan_for_secret_values(
                (observation.evidence, observation.audit_material),
                self.configuration.secret_canaries,
            )
            if leaked:
                return self._result(
                    scenario,
                    CheckStatus.FAIL,
                    started,
                    "Conformance evidence exposed a configured secret canary.",
                    evidence={"leaked_canary_count": len(leaked)},
                )
        except asyncio.TimeoutError:
            return self._result(
                scenario,
                CheckStatus.ERROR,
                started,
                "Conformance scenario exceeded its bounded timeout.",
                exception_type="builtins.TimeoutError",
            )
        except AssertionError:
            return self._result(
                scenario,
                CheckStatus.FAIL,
                started,
                "Boundary invariant was not preserved.",
            )
        except Exception as exc:  # noqa: BLE001 - exception messages may contain secrets
            return self._result(
                scenario,
                CheckStatus.ERROR,
                started,
                "Conformance scenario raised an unexpected exception.",
                exception_type=f"{type(exc).__module__}.{type(exc).__qualname__}",
            )
        return self._result(
            scenario,
            CheckStatus.PASS,
            started,
            observation.summary,
            evidence=observation.evidence,
        )

    @staticmethod
    def _result(
        scenario: Scenario,
        status: CheckStatus,
        started_ns: int,
        summary: str,
        *,
        evidence: dict[str, Any] | None = None,
        exception_type: str | None = None,
    ) -> CheckResult:
        duration_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        return CheckResult(
            check_id=scenario.check_id,
            invariant=scenario.invariant,
            status=status,
            severity=Severity(scenario.severity),
            summary=summary,
            duration_ms=duration_ms,
            evidence=evidence or {},
            remediation=None if status is CheckStatus.PASS else scenario.remediation,
            exception_type=exception_type,
        )

    @staticmethod
    def _skip_for_capability(scenario: Scenario, capability: str) -> CheckResult:
        return CheckResult(
            check_id=scenario.check_id,
            invariant=scenario.invariant,
            status=CheckStatus.SKIP,
            severity=Severity(scenario.severity),
            summary="Required implementation capability is unavailable.",
            duration_ms=0,
            evidence={"capability": capability},
            remediation="Implement and declare the required capability before certification.",
        )
