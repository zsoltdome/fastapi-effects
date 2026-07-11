from __future__ import annotations

import pytest

from fastapi_mergen.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
    decide,
)
from fastapi_mergen.testing import ReferenceBoundaryDriver, assert_certified


@pytest.mark.parametrize("profile", list(CertificationProfile))
async def test_reference_driver_certifies_every_profile(profile: CertificationProfile) -> None:
    report = await ConformanceRunner(RunnerConfiguration(profile=profile)).run(
        ReferenceBoundaryDriver()
    )
    decision = assert_certified(report)
    assert decision == decide(report)
    assert report.certified
    assert report.counts()["pass"] > 0
    assert not decision.missing_invariants


async def test_fail_fast_stops_after_first_detected_failure() -> None:
    from fastapi_mergen.testing import Fault

    report = await ConformanceRunner(
        RunnerConfiguration(profile=CertificationProfile.CORE, fail_fast=True)
    ).run(ReferenceBoundaryDriver(faults=(Fault.COMMIT_PARTIAL,)))
    assert not report.certified
    assert len(report.results) == 1
    assert report.results[0].status.value in {"fail", "error"}


async def test_configured_secret_canary_fails_closed() -> None:
    from fastapi_mergen.conformance.contract import Invariant
    from fastapi_mergen.testing import ReferenceBoundaryDriver

    class CanaryDriver(ReferenceBoundaryDriver):
        async def public_evidence(self):  # type: ignore[no-untyped-def]
            return {"diagnostic": "deploy-secret-value"}

    report = await ConformanceRunner(
        RunnerConfiguration(
            profile=CertificationProfile.SECURITY,
            secret_canaries=("deploy-secret-value",),
        )
    ).run(CanaryDriver())
    result = next(
        item
        for item in report.results
        if item.invariant is Invariant.SECRET_MINIMIZATION
    )
    assert result.status.value == "fail"
    assert "deploy-secret-value" not in repr(report.as_dict())


async def test_manifest_failure_still_closes_driver() -> None:
    from fastapi_mergen.errors import MergenConfigurationError

    class BrokenManifestDriver:
        closed = False

        @property
        def manifest(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("secret adapter detail")

        async def reset(self) -> None:
            return None

        async def close(self) -> None:
            self.closed = True

        async def public_evidence(self):  # type: ignore[no-untyped-def]
            return {}

    driver = BrokenManifestDriver()
    with pytest.raises(MergenConfigurationError, match="manifest could not be read") as caught:
        await ConformanceRunner().run(driver)  # type: ignore[arg-type]
    assert driver.closed
    assert "secret adapter detail" not in str(caught.value)


async def test_cleanup_failure_prevents_certification() -> None:
    from fastapi_mergen.conformance import CheckStatus

    class CleanupFailureDriver(ReferenceBoundaryDriver):
        async def close(self) -> None:
            raise RuntimeError("secret cleanup detail")

    report = await ConformanceRunner(
        RunnerConfiguration(profile=CertificationProfile.CORE)
    ).run(CleanupFailureDriver())
    cleanup = next(item for item in report.results if item.check_id == "runner.cleanup")
    assert cleanup.status is CheckStatus.ERROR
    assert not report.certified
    assert "secret cleanup detail" not in repr(report.as_dict())


def test_runner_rejects_non_finite_timeout() -> None:
    from fastapi_mergen.errors import MergenConfigurationError

    with pytest.raises(MergenConfigurationError, match="timeout"):
        RunnerConfiguration(check_timeout_seconds=float("nan"))
