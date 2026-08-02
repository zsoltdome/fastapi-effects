from __future__ import annotations

from fastapi_mergen import AuthorizationMode, EffectContext, Mergen, Principal, RetryPolicy


async def principal_provider(request: object) -> Principal:
    del request
    raise AssertionError


async def handler(context: EffectContext[object]) -> None:
    del context


def test_route_snapshot_is_complete_and_byte_stable() -> None:
    mergen = Mergen(principal_provider=principal_provider)
    mergen.route(event_type="invoice.created", route_key="invoice.render", version=1).to_handler(
        handler,
        required_scopes={"invoice:read"},
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=60,
        retry_policy=RetryPolicy(name="invoice-render"),
    )
    mergen.freeze()
    route = mergen.routes[0]

    assert route.snapshot_bytes() == route.snapshot_bytes()
    assert route.to_snapshot()["destination"] == {"kind": "handler", "key": "invoice.render"}
    assert route.to_snapshot()["authority"] == {
        "mode": "snapshot",
        "required_scopes": ["invoice:read"],
        "service_policy": None,
        "service_capabilities": None,
        "maximum_snapshot_age_seconds": 60,
    }
