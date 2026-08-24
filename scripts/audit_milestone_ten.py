"""Static completeness audit for the Taskiq external-executor alpha."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "docs/adr/ADR-011-taskiq-handoff.md",
    "src/fastapi_mergen/executors/protocols.py",
    "src/fastapi_mergen/executors/taskiq/models.py",
    "src/fastapi_mergen/executors/taskiq/store.py",
    "src/fastapi_mergen/executors/taskiq/envelope.py",
    "src/fastapi_mergen/executors/taskiq/adapter.py",
    "src/fastapi_mergen/executors/taskiq/worker.py",
    "src/fastapi_mergen/executors/taskiq/recovery.py",
    "src/fastapi_mergen/postgres/migrations/versions/0003_taskiq.py",
    "src/fastapi_mergen/testing/taskiq_driver.py",
    "src/fastapi_mergen/testing/taskiq_worker_fixture.py",
    "tests/conformance/test_real_taskiq.py",
    "tests/conformance/test_real_complete.py",
    "tests/integration/test_taskiq_worker_claim.py",
    "docs/integrations/taskiq.md",
)


def main() -> int:
    missing = [item for item in REQUIRED if not (ROOT / item).is_file()]
    adapter = (ROOT / "src/fastapi_mergen/executors/taskiq/adapter.py").read_text()
    certification = (ROOT / "src/fastapi_mergen/testing/taskiq_driver.py").read_text()
    forbidden = [item for item in ("SimpleRetryMiddleware", "wait_result(") if item in adapter]
    missing_boundaries = [
        item
        for item in ("RedisStreamBroker", "create_subprocess_exec", "taskiq_worker_fixture")
        if item not in certification
    ]
    if "InMemoryBroker" in certification:
        forbidden.append("InMemoryBroker certification")
    if missing or forbidden or missing_boundaries:
        for item in missing:
            print(f"missing: {item}")
        for item in forbidden:
            print(f"forbidden Taskiq ownership: {item}")
        for item in missing_boundaries:
            print(f"missing Taskiq certification boundary: {item}")
        return 1
    print("Milestone 10 Taskiq implementation audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
