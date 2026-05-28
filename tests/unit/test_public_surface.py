from __future__ import annotations

import fastapi_mergen


def test_root_exports_are_intentional() -> None:
    assert fastapi_mergen.__all__ == ["__version__"]
    assert not hasattr(fastapi_mergen, "Repository")
    assert not hasattr(fastapi_mergen, "SQLExpression")
