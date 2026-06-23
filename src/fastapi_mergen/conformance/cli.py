"""Command handlers for executable Boundary Contract conformance."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path

from fastapi_mergen.conformance.contract import CertificationProfile, SPEC_RESOURCE
from fastapi_mergen.conformance.loading import load_driver
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.reporters import ReportFormat, render_report, write_report
from fastapi_mergen.conformance.runner import ConformanceRunner, RunnerConfiguration
from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.testing.reference import Fault, ReferenceBoundaryDriver


def configure_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Attach the conformance command tree to the root CLI parser."""

    command = commands.add_parser("conformance", help="Run Boundary Contract assurance")
    subcommands = command.add_subparsers(dest="conformance_command")

    run = subcommands.add_parser("run", help="Run a profile against a trusted driver")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--adapter", help="Trusted module:factory driver specification")
    source.add_argument("--reference", action="store_true", help="Use the specification oracle")
    run.add_argument(
        "--profile",
        choices=[profile.value for profile in CertificationProfile],
        default=CertificationProfile.CORE.value,
    )
    run.add_argument(
        "--format",
        choices=[item.value for item in ReportFormat],
        default=ReportFormat.JSON.value,
    )
    run.add_argument("--output", default="-", help="Output path or - for standard output")
    run.add_argument("--timeout", type=float, default=None, help="Per-check timeout in seconds")
    run.add_argument("--fail-fast", action="store_true")
    run.add_argument(
        "--fault",
        action="append",
        default=[],
        choices=[fault.value for fault in Fault],
        help="Reference-driver fault injection for suite validation",
    )

    manifest = subcommands.add_parser("manifest", help="Print or validate a driver manifest")
    manifest_source = manifest.add_mutually_exclusive_group(required=True)
    manifest_source.add_argument("--adapter")
    manifest_source.add_argument("--reference", action="store_true")
    manifest.add_argument("--input", help="Validate a manifest JSON file instead of the driver")

    subcommands.add_parser("spec", help="Print the packaged machine-readable contract")


def execute(args: argparse.Namespace) -> int:
    """Execute a parsed conformance command."""

    if args.conformance_command == "run":
        try:
            report = asyncio.run(_run(args))
            rendered = render_report(report, args.format)
            if args.output == "-":
                print(rendered, end="")
            else:
                write_report(args.output, rendered)
            return 0 if report.certified else 1
        except MergenConfigurationError as exc:
            print(f"configuration error: {exc}")
            return 2
    if args.conformance_command == "manifest":
        try:
            if args.input:
                manifest = CapabilityManifest.from_json(Path(args.input).read_bytes())
            else:
                driver = asyncio.run(_driver(args))
                manifest = driver.manifest
                asyncio.run(driver.close())
            print(manifest.to_json())
            return 0
        except (OSError, MergenConfigurationError) as exc:
            print(f"manifest error: {exc}")
            return 2
    if args.conformance_command == "spec":
        package = files("fastapi_mergen.conformance")
        print(package.joinpath(SPEC_RESOURCE).read_text(encoding="utf-8"), end="")
        return 0
    return 2


async def _driver(args: argparse.Namespace) -> ReferenceBoundaryDriver | object:
    if args.reference:
        return ReferenceBoundaryDriver(faults=getattr(args, "fault", ()))
    return await load_driver(args.adapter)


async def _run(args: argparse.Namespace):
    driver = await _driver(args)
    configuration = RunnerConfiguration(
        profile=CertificationProfile(args.profile),
        check_timeout_seconds=args.timeout,
        fail_fast=args.fail_fast,
    )
    return await ConformanceRunner(configuration).run(driver)  # type: ignore[arg-type]
