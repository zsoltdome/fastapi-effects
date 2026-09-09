"""Trusted factory loader for polling relay operation."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import signal
from collections.abc import Callable

from fastapi_mergen.postgres.relay import PollingRelay


def run_relay(factory_path: str) -> int:
    try:
        return asyncio.run(_run(factory_path))
    except KeyboardInterrupt:
        # Windows and embedded loops may not support add_signal_handler().
        return 130


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
    remove_signal_handlers = _install_stop_signal_handlers(relay)
    try:
        await relay.run()
    finally:
        remove_signal_handlers()
    return 0


def _install_stop_signal_handlers(relay: PollingRelay) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, relay.request_stop)
        except (NotImplementedError, RuntimeError):
            continue
        installed.append(signum)

    def remove() -> None:
        for signum in installed:
            loop.remove_signal_handler(signum)

    return remove


__all__ = ["run_relay"]
