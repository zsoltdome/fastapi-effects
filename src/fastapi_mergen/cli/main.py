"""Console entry point for FastAPI-Mergen."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from fastapi_mergen._version import __version__


def _not_available(command: str) -> int:
    print(
        f"{command} is reserved by the Milestone 1 contract and is implemented in a later "
        "milestone. No database operation was performed."
    )
    return 2


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

    commands.add_parser("doctor", help="Run live deployment diagnostics (Milestone 2)")

    schema = commands.add_parser("schema", help="Inspect schema compatibility")
    schema_commands = schema.add_subparsers(dest="schema_command")
    schema_commands.add_parser("check", help="Check schema compatibility (Milestone 2)")

    relay = commands.add_parser("relay", help="Operate the delivery relay")
    relay_commands = relay.add_subparsers(dest="relay_command")
    relay_commands.add_parser("run", help="Run polling relay (Milestone 2)")
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
        return _not_available("fastapi-mergen doctor")
    if args.command == "schema" and args.schema_command == "check":
        return _not_available("fastapi-mergen schema check")
    if args.command == "relay" and args.relay_command == "run":
        return _not_available("fastapi-mergen relay run")
    parser.error("a subcommand is required")
    return 2
