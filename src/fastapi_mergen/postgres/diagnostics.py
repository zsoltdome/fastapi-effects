"""Bounded live PostgreSQL safety and compatibility probes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.sqlalchemy.models import SCHEMA


class DiagnosticStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    code: str
    status: DiagnosticStatus
    summary: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DiagnosticCheck, ...]

    @property
    def healthy(self) -> bool:
        return all(check.status is not DiagnosticStatus.FAIL for check in self.checks)


async def inspect_runtime_database(
    engine: AsyncEngine,
    *,
    expected_revision: int = 1,
    expected_role: str | None = None,
    application_table: str | None = None,
    roles: RuntimeRoles | None = None,
) -> DoctorReport:
    """Inspect the credentials actually configured on an async engine."""
    configured = roles or RuntimeRoles()
    checks: list[DiagnosticCheck] = []
    async with engine.connect() as connection:
        role = (
            await connection.execute(
                text(
                    "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).one()
        role_name = str(role.rolname)
        checks.append(
            _check(
                "role.expected",
                expected_role is None or role_name == expected_role,
                "Connected role matches the configured runtime role.",
                "Connected role does not match the configured runtime role.",
            )
        )
        checks.append(
            _check(
                "role.not_superuser",
                not bool(role.rolsuper),
                "Runtime role is not a superuser.",
                "Runtime role is a superuser; use a restricted credential.",
            )
        )
        checks.append(
            _check(
                "role.no_bypassrls",
                not bool(role.rolbypassrls),
                "Runtime role cannot bypass row security.",
                "Runtime role has BYPASSRLS; revoke it before use.",
            )
        )

        revision = await connection.scalar(
            text(f"SELECT revision FROM {SCHEMA}.schema_revision WHERE component = 'core'")
        )
        checks.append(
            _check(
                "schema.core_revision",
                revision == expected_revision,
                "Core schema revision is compatible.",
                "Core schema revision is missing or incompatible; run the reviewed migration.",
            )
        )

        table_rows = (
            await connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "pg_get_userbyid(c.relowner) AS owner "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :schema AND c.relname = ANY(:tables)"
                ),
                {"schema": SCHEMA, "tables": ["events", "deliveries", "attempts"]},
            )
        ).all()
        by_table = {str(row.relname): row for row in table_rows}
        for table in ("events", "deliveries", "attempts"):
            row = by_table.get(table)
            checks.append(
                _check(
                    f"rls.{table}",
                    row is not None and bool(row.relrowsecurity) and bool(row.relforcerowsecurity),
                    f"{table} has enabled and forced row security.",
                    f"{table} is missing enabled/forced row security.",
                )
            )
            checks.append(
                _check(
                    f"ownership.{table}",
                    row is not None
                    and str(row.owner) not in {configured.application, configured.relay},
                    f"{table} is not owned by a runtime role.",
                    f"{table} is owned by a runtime role; transfer ownership.",
                )
            )

        policy_rows = (
            await connection.execute(
                text(
                    "SELECT tablename, roles, qual, with_check FROM pg_policies "
                    "WHERE schemaname = :schema"
                ),
                {"schema": SCHEMA},
            )
        ).all()
        for table in ("events", "deliveries", "attempts"):
            app_policies = [
                row
                for row in policy_rows
                if row.tablename == table and configured.application in tuple(row.roles)
            ]
            checks.append(
                _check(
                    f"policy.{table}.application",
                    any(
                        row.qual is not None and row.with_check is not None for row in app_policies
                    ),
                    f"{table} application policy has USING and WITH CHECK.",
                    f"{table} lacks a complete application tenant policy.",
                )
            )

        tenant_setting, subject_setting = await _context_settings(connection)
        checks.append(
            _check(
                "context.missing_denies",
                tenant_setting is None and subject_setting is None,
                "No tenant or subject setting survives checkout by default.",
                "Tenant or subject context leaked into a pooled connection.",
            )
        )

        if role_name == configured.application:
            tenant_isolated = await _tenant_isolation_probe(connection)
            checks.append(
                _check(
                    "rls.live_cross_tenant",
                    tenant_isolated,
                    "Live probe denied cross-tenant and missing-context reads.",
                    "Live tenant-isolation probe failed; inspect role policy and grants.",
                )
            )
            rolled_back_tenant, rolled_back_subject = await _context_settings(connection)
            checks.append(
                _check(
                    "context.rollback_cleanup",
                    rolled_back_tenant is None and rolled_back_subject is None,
                    "Transaction-local tenant and subject context reset after rollback.",
                    "Tenant or subject context survived rollback.",
                )
            )
            await connection.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                {"tenant": str(uuid4())},
            )
            await connection.execute(text("SELECT set_config('mergen.subject_id', 'doctor', true)"))
            await connection.commit()
            committed_tenant, committed_subject = await _context_settings(connection)
            checks.append(
                _check(
                    "context.commit_cleanup",
                    committed_tenant is None and committed_subject is None,
                    "Transaction-local tenant and subject context reset after commit.",
                    "Tenant or subject context survived commit.",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    code="rls.live_cross_tenant",
                    status=DiagnosticStatus.SKIP,
                    summary="Run with application credentials to probe live tenant isolation.",
                )
            )

        if role_name == configured.relay and application_table is not None:
            allowed = await _can_select_application_table(connection, application_table)
            checks.append(
                _check(
                    "relay.application_table_denied",
                    not allowed,
                    "Relay credentials cannot read the configured application table.",
                    "Relay credentials can read the configured application table.",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    code="relay.application_table_denied",
                    status=DiagnosticStatus.SKIP,
                    summary="Supply a relay connection and application table to run this probe.",
                )
            )
    async with engine.connect() as reused:
        reused_tenant, reused_subject = await _context_settings(reused)
        checks.append(
            _check(
                "context.pool_cleanup",
                reused_tenant is None and reused_subject is None,
                "Pooled connection checkout contains no tenant or subject context.",
                "A pooled connection retained tenant or subject context.",
            )
        )
    return DoctorReport(tuple(checks))


async def _tenant_isolation_probe(connection: AsyncConnection) -> bool:
    tenant = uuid4()
    other_tenant = uuid4()
    event_id = uuid4()
    try:
        await connection.execute(
            text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
            {"tenant": str(tenant)},
        )
        await connection.execute(text("SELECT set_config('mergen.subject_id', 'doctor', true)"))
        await connection.execute(
            text(
                f"INSERT INTO {SCHEMA}.events "
                "(tenant_id, event_id, event_type, event_version, canonical_version, "
                "payload, payload_canonical, payload_sha256, principal, occurred_at, created_at) "
                "VALUES (:tenant, :event, 'doctor.probe', 1, 1, CAST('{}' AS jsonb), "
                ":canonical, :digest, CAST(:principal AS jsonb), CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            ),
            {
                "tenant": tenant,
                "event": event_id,
                "canonical": b"fastapi-mergen:canonical-json:v1\n{}",
                "digest": bytes(32),
                "principal": (
                    '{"tenant_id":"'
                    + str(tenant)
                    + '","subject_id":"doctor","scopes":[],"actor_id":null,'
                    '"client_id":null,"issued_at":"2026-01-01T00:00:00Z",'
                    '"authentication_time":null,"expires_at":null,"credential_ref":null}'
                ),
            },
        )
        await connection.execute(
            text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
            {"tenant": str(other_tenant)},
        )
        cross_tenant = await connection.scalar(
            text(f"SELECT event_id FROM {SCHEMA}.events WHERE event_id = :event"),
            {"event": event_id},
        )
        await connection.execute(text("SELECT set_config('mergen.tenant_id', '', true)"))
        missing_context = await connection.scalar(
            text(f"SELECT event_id FROM {SCHEMA}.events WHERE event_id = :event"),
            {"event": event_id},
        )
        return cross_tenant is None and missing_context is None
    except Exception:
        return False
    finally:
        await connection.rollback()


async def _context_settings(connection: AsyncConnection) -> tuple[str | None, str | None]:
    row = (
        await connection.execute(
            text(
                "SELECT nullif(current_setting('mergen.tenant_id', true), '') AS tenant, "
                "nullif(current_setting('mergen.subject_id', true), '') AS subject"
            )
        )
    ).one()
    return row.tenant, row.subject


async def _can_select_application_table(connection: object, table: str) -> bool:
    import re

    if re.fullmatch(r"[a-z_][a-z0-9_]{0,62}\.[a-z_][a-z0-9_]{0,62}", table) is None:
        return True
    try:
        await connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))  # type: ignore[attr-defined]
    except Exception:
        return False
    return True


def _check(code: str, condition: bool, success: str, failure: str) -> DiagnosticCheck:
    return DiagnosticCheck(
        code=code,
        status=DiagnosticStatus.PASS if condition else DiagnosticStatus.FAIL,
        summary=success if condition else failure,
    )


__all__ = [
    "DiagnosticCheck",
    "DiagnosticStatus",
    "DoctorReport",
    "inspect_runtime_database",
]
