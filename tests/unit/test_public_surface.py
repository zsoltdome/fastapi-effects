from __future__ import annotations

import fastapi_mergen


def test_foundation_exports_only_version() -> None:
    assert fastapi_mergen.__all__ == ["__version__"]
    assert not hasattr(fastapi_mergen, "Repository")
    assert not hasattr(fastapi_mergen, "SQLExpression")
