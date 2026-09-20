from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config

from fastapi_effects.cli.main import main
from fastapi_effects.cli.migrations import run_upgrade


def test_cli_help_is_successful() -> None:
    assert main([]) == 0


def test_reserved_command_fails_safely() -> None:
    assert main(["doctor"]) == 2


def test_schema_upgrade_uses_the_packaged_migration_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def upgrade(configuration: object, revision: str) -> None:
        observed["configuration"] = configuration
        observed["revision"] = revision

    monkeypatch.setattr(command, "upgrade", upgrade)
    assert (
        run_upgrade(
            "postgresql+asyncpg://owner:p%40ss@localhost/fastapi_effects",
            create_runtime_roles=False,
        )
        == 0
    )
    configuration = cast(Config, observed["configuration"])
    assert configuration.get_main_option("sqlalchemy.url") == (
        "postgresql+asyncpg://owner:p%40ss@localhost/fastapi_effects"
    )
    assert configuration.attributes["create_runtime_roles"] is False
    assert observed["revision"] == "head"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_relay_cli_drains_on_stop_signal(tmp_path: Path, signum: signal.Signals) -> None:
    ready = tmp_path / "ready"
    environment = os.environ.copy()
    environment["FASTAPI_EFFECTS_SIGNAL_READY_FILE"] = str(ready)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "fastapi_effects",
            "relay",
            "run",
            "--factory",
            "tests.unit._relay_signal_fixture:create_relay",
        ],
        env=environment,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        process.send_signal(signum)
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
