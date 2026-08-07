from __future__ import annotations

import pytest
from pydantic import BaseModel

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.sqlalchemy.canonical import canonical_json_bytes, strict_json_loads


class Payload(BaseModel):
    invoice_id: str
    amount: float


def test_typed_dto_serialization_is_explicit_and_stable() -> None:
    assert canonical_json_bytes(Payload(invoice_id="inv-1", amount=10.5)) == (
        b'{"amount":10.5,"invoice_id":"inv-1"}'
    )


def test_cycles_invalid_unicode_and_excess_nesting_fail_closed() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(MergenConfigurationError, match="cycle"):
        canonical_json_bytes(cycle)
    with pytest.raises(MergenConfigurationError, match="invalid text"):
        canonical_json_bytes({"value": "\ud800"})
    with pytest.raises(MergenConfigurationError):
        strict_json_loads(b"[" * 2000 + b"]" * 2000)
