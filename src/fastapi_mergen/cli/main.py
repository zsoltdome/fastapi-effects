"""Console entry point for FastAPI-Mergen."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from fastapi_mergen._version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the stable command tree without importing optional features."""
    parser = argparse.ArgumentParser(
        prog="fastapi-mergen",
        description="FastAPI-Mergen repository and contract tooling",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")

    from fastapi_mergen.conformance.cli import configure_parser

    configure_parser(commands)

    doctor = commands.add_parser("doctor", help="Run live deployment diagnostics")
    doctor.add_argument("--dsn", help="PostgreSQL DSN (never included in output)")
    doctor.add_argument("--expected-role")
    doctor.add_argument("--application-table")

    schema = commands.add_parser("schema", help="Inspect schema compatibility")
    schema_commands = schema.add_subparsers(dest="schema_command")
    schema_check = schema_commands.add_parser("check", help="Check schema compatibility")
    schema_check.add_argument("--dsn", help="PostgreSQL DSN (never included in output)")
    schema_check.add_argument("--expected-role")

    relay = commands.add_parser("relay", help="Operate the delivery relay")
    relay_commands = relay.add_subparsers(dest="relay_command")
    relay_run = relay_commands.add_parser("run", help="Run polling relay")
    relay_run.add_argument("--factory", required=True, help="Trusted module:callable relay factory")

    webhooks = commands.add_parser("webhooks", help="Inspect webhook configuration")
    webhook_commands = webhooks.add_subparsers(dest="webhook_command")
    endpoint = webhook_commands.add_parser(
        "validate-endpoint", help="Validate URL syntax and registration policy"
    )
    endpoint.add_argument("url")
    endpoint.add_argument("--development", action="store_true")

    command_ledger = commands.add_parser("commands", help="Maintain command idempotency")
    command_operations = command_ledger.add_subparsers(dest="commands_command")
    prune = command_operations.add_parser("prune", help="Prune expired terminal commands")
    prune.add_argument("--dsn", help="PostgreSQL relay DSN (never included in output)")
    prune.add_argument("--before", required=True, help="Timezone-aware ISO-8601 cutoff")
    prune.add_argument("--batch-size", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "conformance":
        from fastapi_mergen.conformance.cli import execute

        return execute(args)
    if args.command == "doctor":
        from fastapi_mergen.cli.doctor import run_doctor

        dsn = args.dsn or os.getenv("MERGEN_DATABASE_DSN")
        if not dsn:
            print("doctor requires --dsn or MERGEN_DATABASE_DSN; no connection was attempted")
            return 2
        return run_doctor(
            dsn,
            expected_role=args.expected_role,
            application_table=args.application_table,
        )
    if args.command == "schema" and args.schema_command == "check":
        from fastapi_mergen.cli.doctor import run_doctor

        dsn = args.dsn or os.getenv("MERGEN_DATABASE_DSN")
        if not dsn:
            print("schema check requires --dsn or MERGEN_DATABASE_DSN")
            return 2
        return run_doctor(dsn, expected_role=args.expected_role)
    if args.command == "relay" and args.relay_command == "run":
        from fastapi_mergen.cli.relay import run_relay

        return run_relay(args.factory)
    if args.command == "webhooks" and args.webhook_command == "validate-endpoint":
        from fastapi_mergen.cli.webhooks import validate_endpoint

        return validate_endpoint(args.url, development=args.development)
    if args.command == "commands" and args.commands_command == "prune":
        from fastapi_mergen.idempotency.cli import run_prune

        dsn = args.dsn or os.getenv("MERGEN_DATABASE_DSN")
        if not dsn:
            print("commands prune requires --dsn or MERGEN_DATABASE_DSN")
            return 2
        return run_prune(dsn, before=args.before, batch_size=args.batch_size)
    parser.error("a subcommand is required")
