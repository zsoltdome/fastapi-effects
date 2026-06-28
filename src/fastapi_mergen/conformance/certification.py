"""Certification decisions derived only from complete report evidence."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi_mergen.conformance.contract import CertificationProfile, profile_invariants
from fastapi_mergen.conformance.models import CheckStatus, ConformanceReport
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.errors import MergenConfigurationError


@dataclass(frozen=True, slots=True)
class CertificationDecision:
    """Stable explanation of one profile certification decision."""

    profile: CertificationProfile
    certified: bool
    missing_invariants: tuple[str, ...]
    failed_checks: tuple[str, ...]
    errored_checks: tuple[str, ...]
    skipped_checks: tuple[str, ...]


def decide(report: ConformanceReport) -> CertificationDecision:
    """Require at least one passing check for every profile invariant."""

    required = profile_invariants(report.profile)
    passed = {
        result.invariant
        for result in report.results
        if result.status is CheckStatus.PASS
    }
    missing = tuple(sorted(item.value for item in required - passed))
    failed = tuple(
        result.check_id for result in report.results if result.status is CheckStatus.FAIL
    )
    errored = tuple(
        result.check_id for result in report.results if result.status is CheckStatus.ERROR
    )
    skipped = tuple(
        result.check_id for result in report.results if result.status is CheckStatus.SKIP
    )
    return CertificationDecision(
        profile=report.profile,
        certified=not missing and not failed and not errored and not skipped,
        missing_invariants=missing,
        failed_checks=failed,
        errored_checks=errored,
        skipped_checks=skipped,
    )


def verify_evidence(
    report: ConformanceReport,
    manifest: CapabilityManifest,
) -> CertificationDecision:
    """Bind archived evidence to its exact capability declaration."""

    if report.manifest_digest != manifest.digest:
        raise MergenConfigurationError(
            "Conformance report does not match the supplied capability manifest."
        )
    required = profile_invariants(report.profile)
    if not required.issubset(manifest.invariants):
        raise MergenConfigurationError(
            "Capability manifest does not declare every invariant in the report profile."
        )
    return decide(report)
