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
    result = next(item for item in report.results if item.invariant is Invariant.SECRET_MINIMIZATION)
    assert result.status.value == "fail"
    assert "deploy-secret-value" not in repr(report.as_dict())
