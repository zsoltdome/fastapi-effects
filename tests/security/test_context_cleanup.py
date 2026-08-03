from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from fastapi_mergen.core.context import current_principal, principal_context
from fastapi_mergen.core.principal import Principal


@pytest.mark.asyncio
async def test_sequential_and_concurrent_principals_do_not_leak() -> None:
    first = Principal(tenant_id=uuid4(), subject_id="user:first")
    second = Principal(tenant_id=uuid4(), subject_id="user:second")

    async def observe(principal: Principal) -> tuple[object, object]:
        with principal_context(principal):
            await asyncio.sleep(0)
            bound = current_principal()
            return bound.tenant_id, bound.subject_id  # type: ignore[union-attr]

    assert await asyncio.gather(observe(first), observe(second)) == [
        (first.tenant_id, first.subject_id),
        (second.tenant_id, second.subject_id),
    ]
    assert current_principal(required=False) is None

    with pytest.raises(RuntimeError), principal_context(first):
        raise RuntimeError("failure")
    assert current_principal(required=False) is None
