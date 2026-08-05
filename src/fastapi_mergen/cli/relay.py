"""Trusted factory loader for polling relay operation."""

from __future__ import annotations

import asyncio
import importlib
import inspect

from fastapi_mergen.postgres.relay import PollingRelay


def run_relay(factory_path: str) -> int:
    return asyncio.run(_run(factory_path))


async def _run(factory_path: str) -> int:
    module_name, separator, attribute = factory_path.partition(":")
    if not separator or not module_name or not attribute:
        print("relay factory must use module:callable syntax")
        return 2
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        value = factory()
        relay = await value if inspect.isawaitable(value) else value
    except Exception:
        print("relay factory could not be loaded")
        return 2
    if not isinstance(relay, PollingRelay):
        print("relay factory must return PollingRelay")
        return 2
    try:
        await relay.run()
    except KeyboardInterrupt:
        relay.request_stop()
    return 0


__all__ = ["run_relay"]
