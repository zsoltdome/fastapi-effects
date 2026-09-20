from __future__ import annotations

from fastapi_effects import AuthorizationMode, EffectContext, FastAPIEffects, Principal, RetryPolicy


async def principal_provider(request: object) -> Principal:
    del request
    raise AssertionError


async def handler(context: EffectContext[object]) -> None:
    del context


def test_route_snapshot_is_complete_and_byte_stable() -> None:
    fastapi_effects = FastAPIEffects(principal_provider=principal_provider)
    fastapi_effects.route(
        event_type="invoice.created", route_key="invoice.render", version=1
    ).to_handler(
        handler,
        required_scopes={"invoice:read"},
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=60,
        retry_policy=RetryPolicy(name="invoice-render"),
    )
    fastapi_effects.freeze()
    route = fastapi_effects.routes[0]

    assert route.snapshot_bytes() == route.snapshot_bytes()
    assert route.to_snapshot()["destination"] == {"kind": "handler", "key": "invoice.render"}
    assert route.to_snapshot()["authority"] == {
        "mode": "snapshot",
        "required_scopes": ["invoice:read"],
        "service_policy": None,
        "service_capabilities": None,
        "maximum_snapshot_age_seconds": 60,
    }
