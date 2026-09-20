from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from fastapi_effects.conformance import (
    Capability,
    CapabilityManifest,
    CertificationProfile,
    CheckResult,
    CheckStatus,
    ConformanceReport,
    Invariant,
    Severity,
)
from fastapi_effects.conformance.contract import profile_invariants, required_capabilities
from fastapi_effects.errors import FastAPIEffectsConfigurationError


def complete_manifest() -> CapabilityManifest:
    return CapabilityManifest(
        adapter_name="Test adapter",
        adapter_version="1.2.3",
        implementation="tests.conformance.adapter",
        capabilities=frozenset(Capability),
        invariants=frozenset(Invariant),
        metadata={"runtime": "test"},
    )


def result(
    invariant: Invariant = Invariant.ATOMIC_INTENT,
    *,
    check_id: str = "atomicity.commit",
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        invariant=invariant,
        status=CheckStatus.PASS,
        severity=Severity.CRITICAL,
        summary="Invariant preserved.",
        duration_ms=1,
        evidence={"count": 1},
    )


def report(results: tuple[CheckResult, ...]) -> ConformanceReport:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    return ConformanceReport(
        profile=CertificationProfile.CORE,
        manifest_digest=complete_manifest().digest,
        results=results,
        started_at=now,
        finished_at=now,
        run_id=UUID("11111111-1111-4111-8111-111111111111"),
    )


def test_manifest_round_trip_is_canonical() -> None:
    manifest = complete_manifest()
    loaded = CapabilityManifest.from_json(manifest.to_json())
    assert loaded == manifest
    assert loaded.digest == manifest.digest
    assert json.loads(manifest.canonical_bytes()) == manifest.as_dict()


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":1,"schema_version":1}',
        "[]",
        b"\xff",
    ],
)
def test_manifest_rejects_non_strict_json(payload: str | bytes) -> None:
    with pytest.raises(FastAPIEffectsConfigurationError):
        CapabilityManifest.from_json(payload)


def test_manifest_rejects_sensitive_metadata() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="sensitive"):
        CapabilityManifest(
            adapter_name="Unsafe adapter",
            adapter_version="1.0",
            implementation="tests.unsafe",
            capabilities=frozenset(),
            invariants=frozenset({Invariant.SECRET_MINIMIZATION}),
            metadata={"access_token": "not-publishable"},
        )


def test_manifest_rejects_missing_prerequisite_capability() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="undeclared capabilities"):
        CapabilityManifest(
            adapter_name="Incomplete adapter",
            adapter_version="1.0",
            implementation="tests.incomplete",
            capabilities=frozenset({Capability.DELIVERY_LEASES}),
            invariants=frozenset({Invariant.STABLE_RETRY_IDENTITY}),
        )


def test_manifest_rejects_boolean_schema_version() -> None:
    value = complete_manifest().as_dict()
    value["schema_version"] = True
    with pytest.raises(FastAPIEffectsConfigurationError, match="schema_version"):
        CapabilityManifest.from_dict(value)  # type: ignore[arg-type]


def test_delivery_invariants_declare_effect_prerequisite() -> None:
    for invariant in (
        Invariant.STABLE_RETRY_IDENTITY,
        Invariant.INDEPENDENT_FANOUT,
        Invariant.REPLAY_ACCOUNTABILITY,
        Invariant.LEASE_FENCING,
    ):
        assert Capability.TRANSACTIONAL_EFFECTS in required_capabilities(invariant)
        assert Capability.DELIVERY_LEASES in required_capabilities(invariant)


def test_report_is_not_certified_with_partial_profile_evidence() -> None:
    partial = report((result(),))
    assert not partial.certified
    assert Invariant.AUTHORITY_PROVENANCE in profile_invariants(partial.profile)


def test_report_round_trip_verifies_digest_and_derived_fields() -> None:
    results = tuple(
        result(invariant, check_id=f"check.{index}")
        for index, invariant in enumerate(
            sorted(profile_invariants(CertificationProfile.CORE), key=lambda item: item.value),
            start=1,
        )
    )
    original = report(results)
    payload = original.as_dict()
    payload["report_digest"] = original.digest
    loaded = ConformanceReport.from_json(json.dumps(payload))
    assert loaded == original
    assert loaded.certified


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("status", "fail", "status"), ("certified", True, "certification")],
)
def test_report_rejects_tampered_derived_field(
    field: str,
    value: object,
    message: str,
) -> None:
    original = report((result(),))
    payload = original.as_dict()
    payload[field] = value
    with pytest.raises(FastAPIEffectsConfigurationError, match=message):
        ConformanceReport.from_dict(payload)


def test_report_rejects_duplicate_check_ids() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="repeats"):
        report((result(), result()))


def test_report_rejects_tampered_digest() -> None:
    original = report((result(),))
    payload = original.as_dict()
    payload["report_digest"] = "0" * 64
    with pytest.raises(FastAPIEffectsConfigurationError, match="digest"):
        ConformanceReport.from_dict(payload)


def test_manifest_rejects_non_string_array_entries_cleanly() -> None:
    value = complete_manifest().as_dict()
    value["capabilities"] = [[Capability.AUTHORIZATION.value]]
    with pytest.raises(FastAPIEffectsConfigurationError, match="contain strings"):
        CapabilityManifest.from_dict(value)  # type: ignore[arg-type]


def test_manifest_rejects_non_finite_json_constants() -> None:
    payload = complete_manifest().as_dict()
    payload["metadata"] = {"duration": float("nan")}
    encoded = json.dumps(payload, allow_nan=True)
    with pytest.raises(FastAPIEffectsConfigurationError, match="non-finite"):
        CapabilityManifest.from_json(encoded)


def test_report_rejects_non_object_result_entries() -> None:
    original = report((result(),))
    payload = original.as_dict()
    payload["results"] = [1]
    with pytest.raises(FastAPIEffectsConfigurationError, match="contain objects"):
        ConformanceReport.from_dict(payload)  # type: ignore[arg-type]


def test_empty_report_fails_closed() -> None:
    empty = report(())
    assert empty.status is CheckStatus.ERROR
    assert not empty.certified


def test_report_rejects_non_finite_json_constants() -> None:
    original = report((result(),))
    payload = original.as_dict()
    payload["environment"] = {"duration": float("inf")}
    encoded = json.dumps(payload, allow_nan=True)
    with pytest.raises(FastAPIEffectsConfigurationError, match="non-finite"):
        ConformanceReport.from_json(encoded)


def test_manifest_rejects_oversized_json() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="size limit"):
        CapabilityManifest.from_json(" " * (256 * 1024 + 1))


def test_report_rejects_oversized_json() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="size limit"):
        ConformanceReport.from_json(" " * (8 * 1024 * 1024 + 1))


def test_report_rejects_excessive_result_count() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    with pytest.raises(FastAPIEffectsConfigurationError, match="too many results"):
        ConformanceReport(
            profile=CertificationProfile.CORE,
            manifest_digest=complete_manifest().digest,
            results=(result(),) * 2049,
            started_at=now,
            finished_at=now,
        )


@pytest.mark.parametrize("loader", [CapabilityManifest.from_json, ConformanceReport.from_json])
def test_evidence_loader_rejects_non_text_payload(loader: object) -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="text or bytes"):
        loader(123)  # type: ignore[operator]
