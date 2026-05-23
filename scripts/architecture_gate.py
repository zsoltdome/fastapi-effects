#!/usr/bin/env python3
"""Fail when the Milestone 1 repository violates frozen scope or API rules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "fastapi_mergen"
FORBIDDEN_PACKAGES = {"idempotency", "mcp", "queue", "tasks", "workflow", "workflows"}
REQUIRED_ADRS = {
    "0001-trust-model.md",
    "0002-explicit-uow-transaction.md",
    "0003-event-delivery-attempt-model.md",
    "0004-routing-and-policy-snapshots.md",
    "0005-relay-state-machine.md",
}


def _root_exports() -> set[str]:
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if not isinstance(node.value, ast.List):
                        raise AssertionError("__all__ must be a literal list")
                    return {
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    }
    raise AssertionError("root __all__ is missing")


def main() -> int:
    package_dirs = {path.name for path in PACKAGE.iterdir() if path.is_dir()}
    forbidden = package_dirs & FORBIDDEN_PACKAGES
    if forbidden:
        raise AssertionError(f"out-of-scope packages exist: {sorted(forbidden)}")
    if (ROOT / "src" / "mergen").exists():
        raise AssertionError("occupied top-level 'mergen' import must not exist")

    exports = _root_exports()
    forbidden_exports = {"Repository", "SQLExpression", "DBAPIConnection", "HTTPClient"}
    if exports & forbidden_exports:
        raise AssertionError(f"internal symbols leaked: {sorted(exports & forbidden_exports)}")

    adr_dir = ROOT / "docs" / "adr"
    if adr_dir.exists():
        missing = REQUIRED_ADRS - {path.name for path in adr_dir.glob("*.md")}
        if missing:
            raise AssertionError(f"required ADRs missing: {sorted(missing)}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    forbidden_claim = "guarantees exactly-once".lower()
    if forbidden_claim in readme:
        raise AssertionError("README contains a generic exactly-once claim")
    print("Milestone 1 architecture gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
