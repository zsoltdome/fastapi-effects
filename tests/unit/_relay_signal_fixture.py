"""Importable no-database relay factory used by the signal subprocess test."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi_effects.postgres.relay import PollingRelay, RelayConfig


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        del args


class _Sessions:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _Leases:
    async def reconcile_expired(self, session: object, **kwargs: object) -> int:
        del session, kwargs
        return 0

    async def claim(self, session: object, **kwargs: object) -> tuple[()]:
        del session, kwargs
        return ()


class _Sink:
    async def execute(self, claim: object) -> None:
        del claim


class _ReadyPollingRelay(PollingRelay):
    async def run(self) -> None:
        ready_file = os.environ.get("FASTAPI_EFFECTS_SIGNAL_READY_FILE")
        if ready_file:
            await asyncio.to_thread(Path(ready_file).touch)
        await super().run()


def create_relay() -> PollingRelay:
    return _ReadyPollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=_Sink(),
        leases=_Leases(),  # type: ignore[arg-type]
        config=RelayConfig(poll_interval_seconds=0.01, shutdown_grace_seconds=0.05),
    )
