from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from fastapi_effects import Principal
from fastapi_effects.delegation.keys import SigningKey
from fastapi_effects.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_effects.errors import AuthorizationDenied, FastAPIEffectsConfigurationError


class UnavailableKeyProvider:
    def signing_key(self, now: datetime) -> SigningKey:
        del now
        raise FastAPIEffectsConfigurationError("Delegation signing key provider is unavailable.")

    def verification_key(self, key_id: str, now: datetime) -> SigningKey | None:
        del key_id, now
        raise OSError("injected key-provider outage")


def test_key_provider_outage_denies_verification_and_stops_issuance() -> None:
    provider = UnavailableKeyProvider()
    principal = Principal(
        tenant_id=uuid4(),
        subject_id="chaos",
        scopes=frozenset({"invoice:write"}),
    )
    issuer = DelegationIssuer(issuer="chaos", keys=provider)
    with pytest.raises(FastAPIEffectsConfigurationError, match="unavailable"):
        issuer.mint(
            principal=principal,
            audience="billing",
            method="POST",
            path="/charge",
            scopes=principal.scopes,
            ttl=timedelta(seconds=30),
        )
    verifier = DelegationVerifier(issuer="chaos", keys=provider)
    with pytest.raises(AuthorizationDenied):
        verifier.verify(
            token="not-a-credential",
            audience="billing",
            method="POST",
            path="/charge",
            required_scopes=frozenset(),
        )


def test_chaos_manifest_covers_required_boundaries_without_exactly_once_claims() -> None:
    manifest = json.loads(Path(__file__).with_name("scenarios.json").read_text(encoding="utf-8"))
    scenario_ids = {item["id"] for item in manifest["scenarios"]}
    assert {
        "before-command-commit",
        "remote-webhook-success-before-finalize",
        "taskiq-worker-expires-before-finalize",
        "delegation-key-provider-outage",
        "database-connection-loss-transaction-boundary",
        "database-restart",
        "database-failover-ambiguous-commit",
    } <= scenario_ids
    assert "exactly-once" not in json.dumps(manifest).lower()


def test_operator_restart_rehearsal_has_pairwise_passing_evidence() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(Path(__file__).with_name("scenarios.json").read_text(encoding="utf-8"))
    restart = next(item for item in manifest["scenarios"] if item["id"] == "database-restart")
    rehearsal = restart["rehearsal"]
    assert (root / rehearsal["script"]).is_file()
    reports = [
        json.loads((root / evidence).read_text(encoding="utf-8"))
        for evidence in rehearsal["evidence"]
    ]
    assert {report["expected_major"] for report in reports} == {16, 18}
    assert all(
        report["result"] == "pass"
        and report["restart_observed"]
        and report["schema_compatible"]
        and report["doctor_healthy"]
        and report["event_identity_preserved"]
        and report["delivery_identity_preserved"]
        for report in reports
    )
