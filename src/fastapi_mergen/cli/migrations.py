"""Run the migrations bundled in the installed distribution."""

from __future__ import annotations

from importlib.resources import as_file, files

from alembic import command
from alembic.config import Config

from fastapi_mergen.postgres.roles import RuntimeRoles


def run_upgrade(
    dsn: str,
    *,
    roles: RuntimeRoles | None = None,
    create_runtime_roles: bool = True,
) -> int:
    """Upgrade the installed schema to head using migration-owner credentials."""

    resource = files("fastapi_mergen.postgres.migrations").joinpath("alembic.ini")
    with as_file(resource) as configuration_path:
        configuration = Config(str(configuration_path))
        # Alembic Config uses interpolation; preserve percent-encoded DSN bytes.
        configuration.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
        configuration.attributes["runtime_roles"] = roles or RuntimeRoles()
        configuration.attributes["create_runtime_roles"] = create_runtime_roles
        command.upgrade(configuration, "head")
    return 0


__all__ = ["run_upgrade"]
