from __future__ import annotations

from uuid import uuid4

from fastapi_effects.webhooks.secrets import CreatedWebhookSecret, MasterKey, SigningSecret


def test_secret_values_are_absent_from_repr() -> None:
    canary = "secret-canary-never-log"
    created = CreatedWebhookSecret(
        secret_set_id=uuid4(),
        version=1,
        plaintext=canary,
    )
    signing = SigningSecret(version=1, material=canary.encode())
    master = MasterKey(key_id="test", material=b"m" * 32)

    assert canary not in repr(created)
    assert canary not in repr(signing)
    assert "mmmm" not in repr(master)
