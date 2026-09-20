"""Keep capability claims aligned with reachable runtime behavior."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_advertised_core_runtime_contains_no_reachable_stub() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    runtime_sources = (
        ROOT / "src" / "fastapi_effects" / "postgres",
        ROOT / "src" / "fastapi_effects" / "sqlalchemy",
        ROOT / "src" / "fastapi_effects" / "handlers",
    )
    assert "Real PostgreSQL transactional runtime | Implemented" in readme
    for source_root in runtime_sources:
        for path in source_root.rglob("*.py"):
            assert "raise MilestoneNotImplementedError" not in path.read_text(encoding="utf-8")
