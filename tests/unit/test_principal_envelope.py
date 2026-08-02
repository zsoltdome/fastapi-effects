from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fastapi_mergen.core.principal import Principal, PrincipalEnvelope
from fastapi_mergen.errors import MergenConfigurationError


def test_principal_envelope_round_trip_and_repr_minimize_credentials() -> None:
    now = datetime.now(UTC)
    principal = Principal(
        tenant_id=uuid4(),
        subject_id="user:42",
        actor_id="operator:7",
        client_id="client:web",
        scopes=frozenset({"invoice:read", "invoice:write"}),
        issued_at=now,
        authentication_time=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=5),
        credential_ref="vault:opaque-reference",
    )

    envelope = principal.to_envelope()
    assert Principal.from_envelope(envelope) == principal
    assert Principal.from_envelope(envelope.to_dict()) == principal
    assert "vault:opaque-reference" not in repr(principal)
    assert "vault:opaque-reference" not in repr(envelope)


def test_principal_envelope_rejects_credential_like_extras() -> None:
    value = Principal(tenant_id=uuid4(), subject_id="user:42").to_envelope().to_dict()
    value["authorization"] = "Bearer secret"
    with pytest.raises(MergenConfigurationError, match="unsupported fields"):
        PrincipalEnvelope.from_dict(value)
