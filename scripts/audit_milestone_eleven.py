"""Static completeness audit for transactional command idempotency."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "docs/adr/ADR-012-command-idempotency.md",
    "docs/reference/command-idempotency.md",
    "docs/operations/command-idempotency.md",
    "src/fastapi_mergen/idempotency/models.py",
    "src/fastapi_mergen/idempotency/fingerprint.py",
    "src/fastapi_mergen/idempotency/request.py",
    "src/fastapi_mergen/idempotency/store.py",
    "src/fastapi_mergen/idempotency/command.py",
    "src/fastapi_mergen/idempotency/responses.py",
    "src/fastapi_mergen/postgres/command_schema.py",
    "src/fastapi_mergen/postgres/migrations/versions/0004_commands.py",
    "src/fastapi_mergen/testing/idempotency_driver.py",
    "tests/conformance/test_real_commands.py",
    "tests/integration/test_command_concurrency.py",
    "tests/integration/test_idempotent_endpoint.py",
)


def main() -> int:
    missing = [item for item in REQUIRED if not (ROOT / item).is_file()]
    sources = "\n".join(
        (ROOT / item).read_text(encoding="utf-8")
        for item in REQUIRED
        if item.endswith(".py") and (ROOT / item).is_file()
    )
    required_markers = (
        "pg_advisory_xact_lock",
        "Idempotency-Replayed",
        "FOR UPDATE SKIP LOCKED",
        "guard_command_mutation",
    )
    absent_markers = [marker for marker in required_markers if marker not in sources]
    if missing or absent_markers:
        for item in missing:
            print(f"missing: {item}")
        for marker in absent_markers:
            print(f"missing invariant marker: {marker}")
        return 1
    print("Milestone 11 command-idempotency implementation audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
