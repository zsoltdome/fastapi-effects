from __future__ import annotations

import pytest

from fastapi_mergen.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_mergen.testing.delegation_driver import RealDelegationBoundaryDriver

pytestmark = pytest.mark.conformance


@pytest.mark.asyncio
async def test_real_bridge_and_verifier_certify_delegation_profile() -> None:
    report = await ConformanceRunner(
        RunnerConfiguration(profile=CertificationProfile.DELEGATION)
    ).run(RealDelegationBoundaryDriver())
    failures = [
        f"{result.check_id}: {result.status.value} ({result.exception_type})"
        for result in report.results
        if result.status.value not in {"passed", "not_applicable"}
    ]
    assert report.certified, "\n".join(failures)
