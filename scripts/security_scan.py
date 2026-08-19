#!/usr/bin/env python3
"""Offline high-confidence secret and dependency-license policy checks."""

from __future__ import annotations

import importlib.metadata
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
)
FORBIDDEN_LICENSES = ("AGPL", "SSPL", "BUSL")


def _metadata_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(item for item in value if isinstance(item, str))
    return ""


def tracked_files() -> tuple[Path, ...]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return tuple(ROOT / item.decode() for item in output.split(b"\0") if item)


def main() -> int:
    violations: list[str] = []
    for path in tracked_files():
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            violations.append(f"high-confidence secret pattern: {path.relative_to(ROOT)}")
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata.json
        license_text = " ".join(
            (
                _metadata_text(metadata.get("license_expression")),
                _metadata_text(metadata.get("license")),
            )
        ).upper()
        if any(license_name in license_text for license_name in FORBIDDEN_LICENSES):
            violations.append(
                f"forbidden dependency license: {distribution.metadata['Name']} {license_text}"
            )
    if violations:
        raise SystemExit("\n".join(violations))
    print("Offline secret and forbidden-license scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
