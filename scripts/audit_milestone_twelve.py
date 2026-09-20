"""Static completeness audit for delegation and FastMCP integration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "docs/adr/ADR-013-delegation.md",
    "docs/concepts/delegation-threat-model.md",
    "docs/operations/delegation-keys.md",
    "docs/integrations/fastmcp.md",
    "src/fastapi_effects/delegation/models.py",
    "src/fastapi_effects/delegation/keys.py",
    "src/fastapi_effects/delegation/signing.py",
    "src/fastapi_effects/delegation/targets.py",
    "src/fastapi_effects/delegation/bridge.py",
    "src/fastapi_effects/delegation/fastapi.py",
    "src/fastapi_effects/testing/delegation_driver.py",
    "tests/conformance/test_real_delegation.py",
    "tests/security/test_delegation_end_to_end.py",
    "examples/fastmcp_delegation/app.py",
)


def main() -> int:
    missing = [item for item in REQUIRED if not (ROOT / item).is_file()]
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    required_markers = ("fastmcp>=3.4.7,<4", "fastapi>=0.141,<0.142", "starlette>=1.0.1,<2")
    absent = [marker for marker in required_markers if marker not in project]
    bridge = (ROOT / "src/fastapi_effects/delegation/bridge.py").read_text(encoding="utf-8")
    if "forwarded_headers" not in bridge or "repr=False" not in bridge:
        absent.append("credential-safe bridge allowlist")
    if missing or absent:
        for item in missing:
            print(f"missing: {item}")
        for marker in absent:
            print(f"missing integration marker: {marker}")
        return 1
    print("Milestone 12 delegation/FastMCP implementation audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
