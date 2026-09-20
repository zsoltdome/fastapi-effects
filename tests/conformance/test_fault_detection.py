from __future__ import annotations

import pytest

from fastapi_effects.conformance import CertificationProfile, ConformanceRunner, RunnerConfiguration
from fastapi_effects.testing import Fault, ReferenceBoundaryDriver


@pytest.mark.parametrize("fault", list(Fault))
async def test_each_reference_fault_prevents_complete_certification(fault: Fault) -> None:
    report = await ConformanceRunner(
        RunnerConfiguration(profile=CertificationProfile.COMPLETE)
    ).run(ReferenceBoundaryDriver(faults=(fault,)))
    assert not report.certified, fault.value
    assert any(result.status.value != "pass" for result in report.results)
