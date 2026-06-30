"""Trusted driver factories used by CLI loading tests."""

from __future__ import annotations

from fastapi_mergen.testing import ReferenceBoundaryDriver


def create_driver() -> ReferenceBoundaryDriver:
    return ReferenceBoundaryDriver()


async def create_async_driver() -> ReferenceBoundaryDriver:
    return ReferenceBoundaryDriver()
