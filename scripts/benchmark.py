#!/usr/bin/env python3
"""Run a disposable, versioned PostgreSQL benchmark and write bounded JSON evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from fastapi import FastAPI, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.postgres import provision_test_database

from fastapi_effects import (
    AuthorizationMode,
    Event,
    FastAPIEffectsUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_effects import __version__ as fastapi_effects_version
from fastapi_effects.core.routing import RouteSpecification
from fastapi_effects.errors import RetryableDeliveryError
from fastapi_effects.idempotency import CommandContext, CommandIdentity, RequestFingerprint
from fastapi_effects.idempotency.responses import CapturedResponse
from fastapi_effects.idempotency.store import CommandStore
from fastapi_effects.postgres import PostgresStore
from fastapi_effects.postgres.command_schema import install_command_schema
from fastapi_effects.postgres.leasing import LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.webhooks.signing import sign_webhook, verify_webhook


class MidpointRandom:
    def uniform(self, lower: float, upper: float) -> float:
        return (lower + upper) / 2


def _percentile(samples: list[float], proportion: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * proportion))]


def _maximum_run(values: list[UUID]) -> int:
    longest = current = 0
    previous: UUID | None = None
    for value in values:
        current = current + 1 if value == previous else 1
        longest = max(longest, current)
        previous = value
    return longest


async def _webhook_transport(count: int) -> tuple[float, int]:
    app = FastAPI()
    accepted: set[str] = set()
    secret = b"b" * 32

    @app.post("/hooks")
    async def receive(request: Request) -> Response:
        body = await request.body()
        headers = dict(request.headers)
        if not verify_webhook(secret=secret, body=body, headers=headers):
            return Response(status_code=401)
        accepted.add(headers["webhook-id"])
        return Response(status_code=202)

    transport = httpx.ASGITransport(app=app)
    started = time.perf_counter()
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://receiver.test",
    ) as client:
        for sequence in range(count):
            body = b'{"event":"benchmark"}'
            signed = sign_webhook(
                message_id=f"benchmark-{sequence}",
                timestamp=datetime.now(UTC),
                body=body,
                secrets=(secret,),
            )
            response = await client.post("/hooks", content=body, headers=signed.values)
            if response.status_code != 202:
                raise RuntimeError("Benchmark receiver rejected a signed webhook.")
    return time.perf_counter() - started, len(accepted)


async def _command_call(
    sessions: async_sessionmaker[Any],
    principal: Principal,
    identity: CommandIdentity,
    fingerprint: RequestFingerprint,
) -> tuple[float, bool]:
    started = time.perf_counter()
    async with (
        sessions() as session,
        CommandContext(
            session=session,
            principal=principal,
            identity=identity,
            fingerprint=fingerprint,
            ttl=timedelta(seconds=1),
        ) as command,
    ):
        replayed = command.replayed
        if not replayed:
            await command.complete(
                CapturedResponse(
                    status_code=201,
                    media_type="application/json",
                    body=b"{}",
                )
            )
    return time.perf_counter() - started, replayed


async def run_benchmark(admin_dsn: str, *, tenants: int, events_per_tenant: int) -> dict[str, Any]:
    if tenants < 2 or events_per_tenant < 2:
        raise ValueError("benchmark requires at least two tenants and two events per tenant")
    async with provision_test_database(admin_dsn) as database:
        roles = RuntimeRoles(
            migration=database.migration_role,
            application=database.app_role,
            relay=database.relay_role,
        )
        migration_engine = create_async_engine(database.migration_sqlalchemy_dsn)
        app_engine = create_async_engine(database.app_sqlalchemy_dsn)
        relay_engine = create_async_engine(database.relay_sqlalchemy_dsn)
        app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
        relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        route = RouteSpecification(
            event_type="benchmark.created",
            route_key="benchmark.handler",
            version=1,
            destination_kind="handler",
            destination_key="benchmark.handler",
            required_scopes=(),
            authorization=AuthorizationMode.SNAPSHOT,
            service_policy=None,
            service_capabilities=None,
            maximum_snapshot_age_seconds=None,
            retry_policy=RetryPolicy(
                name="benchmark",
                base_delay_seconds=0.01,
                maximum_delay_seconds=1,
                handler_timeout_seconds=1,
                lease_duration_seconds=2,
            ),
        )
        principals = [Principal(tenant_id=uuid4(), subject_id="benchmark") for _ in range(tenants)]
        emission_samples: list[float] = []
        try:
            await install_core_schema(migration_engine, roles=roles)
            await install_command_schema(migration_engine, roles=roles)
            async with migration_engine.connect() as connection:
                postgres_version = str(await connection.scalar(text("SHOW server_version")))

            for principal in principals:
                for sequence in range(events_per_tenant):
                    started = time.perf_counter()
                    async with (
                        app_sessions() as session,
                        FastAPIEffectsUnitOfWork(
                            session=session,
                            principal=principal,
                            store=PostgresStore(),
                            routes=(route,),
                        ) as uow,
                    ):
                        await uow.emit(
                            Event(
                                type="benchmark.created",
                                version=1,
                                data={"sequence": sequence},
                            )
                        )
                    emission_samples.append(time.perf_counter() - started)

            async with migration_engine.connect() as connection:
                backlog_age = await connection.scalar(
                    text(
                        "SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - min(created_at))) "
                        "FROM fastapi_effects.deliveries WHERE state = 'pending'"
                    )
                )

            leases = LeaseRepository(random_source=MidpointRandom())
            claim_order: list[UUID] = []
            claimed_count = 0
            retry_delay = 0.0
            claim_started = time.perf_counter()
            first_claim = True
            while True:
                async with relay_sessions() as session:
                    claimed = await leases.claim(
                        session,
                        now=datetime.now(UTC),
                        batch_size=64,
                        per_tenant=2,
                    )
                if not claimed:
                    break
                claim_order.extend(item.delivery.tenant_id for item in claimed)
                claimed_count += len(claimed)
                for index, claim in enumerate(claimed):
                    async with relay_sessions() as session:
                        if first_claim and index == 0:
                            failed_at = datetime.now(UTC)
                            await leases.fail(
                                session,
                                claim,
                                RetryableDeliveryError(code="benchmark.retry", summary="retry"),
                                now=failed_at,
                            )
                            retry_delay = 0.005
                        else:
                            await leases.succeed(session, claim, now=datetime.now(UTC))
                first_claim = False
            claim_seconds = time.perf_counter() - claim_started

            contention_identity = CommandIdentity.from_key(
                tenant_id=principals[0].tenant_id,
                route_id="benchmark.command",
                method="POST",
                key="same-key",
            )
            fingerprint = RequestFingerprint(version=1, digest=bytes(32))
            command_results = await asyncio.gather(
                *(
                    _command_call(app_sessions, principals[0], contention_identity, fingerprint)
                    for _ in range(16)
                )
            )
            command_samples = [result[0] for result in command_results]

            webhook_count = max(100, tenants * events_per_tenant)
            webhook_seconds, webhook_accepted = await _webhook_transport(webhook_count)

            async with relay_engine.connect() as connection:
                before_size = int(
                    await connection.scalar(
                        text("SELECT pg_total_relation_size('fastapi_effects.commands')")
                    )
                    or 0
                )
            prune_started = time.perf_counter()
            async with relay_sessions() as session:
                pruned = await CommandStore().prune(
                    session,
                    before=datetime.now(UTC) + timedelta(seconds=2),
                    batch_size=100,
                )
            prune_seconds = time.perf_counter() - prune_started
            async with relay_engine.connect() as connection:
                after_size = int(
                    await connection.scalar(
                        text("SELECT pg_total_relation_size('fastapi_effects.commands')")
                    )
                    or 0
                )

            split = events_per_tenant
            thresholds = json.loads(
                (ROOT / "benchmarks" / "thresholds.json").read_text(encoding="utf-8")
            )
            claim_throughput = claimed_count / max(claim_seconds, 1e-9)
            command_p95 = _percentile(command_samples, 0.95) * 1000
            performance_alerts = []
            if claim_throughput < thresholds["minimum_claims_per_second"]:
                performance_alerts.append("claim_throughput")
            if command_p95 > thresholds["maximum_command_contention_p95_ms"]:
                performance_alerts.append("command_contention")
            return {
                "schema_version": 1,
                "environment": {
                    "captured_at": datetime.now(UTC).isoformat(),
                    "cpu_count": os.cpu_count(),
                    "machine": platform.machine(),
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "postgresql": postgres_version,
                    "fastapi_effects": fastapi_effects_version,
                },
                "dataset": {
                    "tenants": tenants,
                    "events_per_tenant": events_per_tenant,
                    "total_deliveries": tenants * events_per_tenant,
                    "payload_bytes": len(b'{"sequence":0}'),
                    "concurrent_command_callers": 16,
                },
                "measurements": {
                    "emission_single_tenant_p50_ms": statistics.median(emission_samples[:split])
                    * 1000,
                    "emission_multi_tenant_p95_ms": _percentile(emission_samples, 0.95) * 1000,
                    "backlog_oldest_age_seconds": float(backlog_age or 0),
                    "claim_throughput_per_second": claim_throughput,
                    "claim_max_consecutive_tenant": _maximum_run(claim_order),
                    "claim_tenants_observed": len(set(claim_order)),
                    "retry_scheduled_delay_seconds": retry_delay,
                    "webhook_transport_per_second": webhook_count / max(webhook_seconds, 1e-9),
                    "command_contention_p95_ms": command_p95,
                    "command_replays": sum(1 for _, replayed in command_results if replayed),
                    "retention_pruned_rows": pruned,
                    "retention_seconds": prune_seconds,
                    "command_index_bytes_before": before_size,
                    "command_index_bytes_after": after_size,
                },
                "correctness": {
                    "all_tenants_claimed": len(set(claim_order)) == tenants,
                    "no_starvation_within_batch_policy": _maximum_run(claim_order) <= 2,
                    "one_command_execution": sum(
                        1 for _, replayed in command_results if not replayed
                    )
                    == 1,
                    "all_webhooks_accepted_once": webhook_accepted == webhook_count,
                },
                "performance_alerts": performance_alerts,
            }
        finally:
            await relay_engine.dispose()
            await app_engine.dispose()
            await migration_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-dsn", default=os.getenv("FASTAPI_EFFECTS_TEST_ADMIN_DSN"))
    parser.add_argument("--tenants", type=int, default=4)
    parser.add_argument("--events-per-tenant", type=int, default=25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.admin_dsn:
        parser.error("--admin-dsn or FASTAPI_EFFECTS_TEST_ADMIN_DSN is required")
    result = asyncio.run(
        run_benchmark(
            args.admin_dsn,
            tenants=args.tenants,
            events_per_tenant=args.events_per_tenant,
        )
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if all(result["correctness"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
