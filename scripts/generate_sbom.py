#!/usr/bin/env python3
"""Generate deterministic CycloneDX JSON for the active locked environment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path


def _component(distribution: importlib.metadata.Distribution) -> dict[str, object]:
    name = distribution.metadata["Name"]
    version = distribution.version
    component: dict[str, object] = {
        "type": "library",
        "bom-ref": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
        "name": name,
        "version": version,
        "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
    }
    license_expression = distribution.metadata.json.get("license_expression")
    if license_expression:
        component["licenses"] = [{"expression": license_expression}]
    return component


def generate() -> dict[str, object]:
    components = sorted(
        (_component(distribution) for distribution in importlib.metadata.distributions()),
        key=lambda item: (str(item["name"]).lower(), str(item["version"])),
    )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:00000000-0000-0000-0000-000000000000",
        "version": 1,
        "metadata": {
            "component": next(item for item in components if item["name"] == "fastapi-effects")
        },
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/sbom.cdx.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(generate(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
