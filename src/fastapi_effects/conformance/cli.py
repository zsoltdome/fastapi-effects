"""Command handlers for executable Boundary Contract conformance."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from importlib.resources import files
from pathlib import Path

from fastapi_effects.conformance.certification import verify_evidence
from fastapi_effects.conformance.contract import SPEC_RESOURCE, CertificationProfile
from fastapi_effects.conformance.loading import load_driver
from fastapi_effects.conformance.manifest import CapabilityManifest
from fastapi_effects.conformance.models import ConformanceReport
from fastapi_effects.conformance.protocols import BoundaryDriver
from fastapi_effects.conformance.reporters import ReportFormat, render_report, write_report
from fastapi_effects.conformance.runner import ConformanceRunner, RunnerConfiguration
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.testing.reference import Fault, ReferenceBoundaryDriver

_DRIVER_CLOSE_TIMEOUT_SECONDS = 5.0


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
        "--secret-canary-env",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Read a secret canary from environment variable NAME and fail if it appears "
            "in public evidence; the value is never written to reports"
        ),
    )
    run.add_argument(
        "--fault",
        action="append",
        default=[],
        choices=[fault.value for fault in Fault],
        help="Reference-driver fault injection for suite validation",
    )

    manifest = subcommands.add_parser("manifest", help="Print or validate a driver manifest")
    manifest_source = manifest.add_mutually_exclusive_group(required=False)
    manifest_source.add_argument("--adapter")
    manifest_source.add_argument("--reference", action="store_true")
    manifest.add_argument("--input", help="Validate a manifest JSON file instead of the driver")

    verify = subcommands.add_parser(
        "verify",
        help="Verify an archived JSON report against its exact manifest",
    )
    verify.add_argument("--manifest", required=True, help="Capability manifest JSON path")
    verify.add_argument("--report", required=True, help="Conformance report JSON path")

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
        except (OSError, FastAPIEffectsConfigurationError) as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2
    if args.conformance_command == "manifest":
        try:
            sources = sum(bool(value) for value in (args.input, args.adapter, args.reference))
            if sources != 1:
                raise FastAPIEffectsConfigurationError(
                    "Choose exactly one of --input, --adapter, or --reference."
                )
            if args.input:
                manifest = CapabilityManifest.from_json(Path(args.input).read_bytes())
            else:
                manifest = asyncio.run(_manifest_from_driver(args))
            print(manifest.to_json())
            return 0
        except (OSError, FastAPIEffectsConfigurationError) as exc:
            print(f"manifest error: {exc}", file=sys.stderr)
            return 2
    if args.conformance_command == "spec":
        package = files("fastapi_effects.conformance")
        print(package.joinpath(SPEC_RESOURCE).read_text(encoding="utf-8"), end="")
        return 0
    if args.conformance_command == "verify":
        try:
            manifest = CapabilityManifest.from_json(Path(args.manifest).read_bytes())
            report = ConformanceReport.from_json(Path(args.report).read_bytes())
            decision = verify_evidence(report, manifest)
            print("certified" if decision.certified else "not-certified")
            return 0 if decision.certified else 1
        except (OSError, FastAPIEffectsConfigurationError) as exc:
            print(f"verification error: {exc}", file=sys.stderr)
            return 2
    return 2


async def _driver(args: argparse.Namespace) -> BoundaryDriver:
    if args.reference:
        return ReferenceBoundaryDriver(faults=getattr(args, "fault", ()))
    if not args.adapter:
        raise FastAPIEffectsConfigurationError("A trusted adapter specification is required.")
    return await load_driver(args.adapter)


def _secret_canaries(args: argparse.Namespace) -> tuple[str, ...]:
    canaries: list[str] = []
    for name in args.secret_canary_env:
        if not name or name not in os.environ:
            raise FastAPIEffectsConfigurationError(
                "Every --secret-canary-env name must identify a present environment variable."
            )
        canaries.append(os.environ[name])
    return tuple(canaries)


async def _run(args: argparse.Namespace) -> ConformanceReport:
    canaries = _secret_canaries(args)
    driver = await _driver(args)
    configuration = RunnerConfiguration(
        profile=CertificationProfile(args.profile),
        check_timeout_seconds=args.timeout,
        fail_fast=args.fail_fast,
        secret_canaries=canaries,
    )
    return await ConformanceRunner(configuration).run(driver)


async def _manifest_from_driver(args: argparse.Namespace) -> CapabilityManifest:
    driver = await _driver(args)
    manifest: CapabilityManifest | None = None
    manifest_error: Exception | None = None
    try:
        manifest = driver.manifest
    except Exception as exc:
        manifest_error = exc
    try:
        await asyncio.wait_for(
            driver.close(),
            timeout=_DRIVER_CLOSE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        if manifest_error is None:
            raise FastAPIEffectsConfigurationError("Conformance driver cleanup failed.") from exc
    if manifest_error is not None:
        raise FastAPIEffectsConfigurationError(
            "Conformance driver manifest could not be read."
        ) from manifest_error
    if manifest is None:
        raise FastAPIEffectsConfigurationError("Conformance driver manifest is unavailable.")
    return manifest
