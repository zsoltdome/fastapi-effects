#!/usr/bin/env python3
"""Audit the Milestone 7 Boundary Contract assurance implementation."""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi_effects._version import __version__  # noqa: E402
from fastapi_effects.conformance import (  # noqa: E402
    CONTRACT_VERSION,
    Capability,
    CertificationProfile,
    ConformanceReport,
    ConformanceRunner,
    Invariant,
    RunnerConfiguration,
    decide,
    verify_evidence,
)
from fastapi_effects.conformance.contract import PROFILE_INVARIANTS  # noqa: E402
from fastapi_effects.conformance.reporters import (  # noqa: E402
    ReportFormat,
    render_report,
    write_report,
)
from fastapi_effects.testing import Fault, ReferenceBoundaryDriver  # noqa: E402

MINIMUM_RELEASE = (0, 6, 0)
AUTHOR_NAME = "zsoltdome"
AUTHOR_EMAIL_SUFFIX = "@users.noreply.github.com"
LEGACY_COMMITTER_NAME = "mergen-institute"
PROJECT_AUTHOR = "Zsolt Döme"
RECOVERED_BASELINE_COMMIT = "ba6659f1eb10dbc3d384669aedd261b7f8ff397d"
RECOVERED_BASELINE_EMAIL = "zsemed@gmail.com"
ALLOWED_BRANCH_PREFIXES = {
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "refactor",
    "test",
}
REQUIRED_PATHS = {
    "src/fastapi_effects/conformance/__init__.py",
    "src/fastapi_effects/conformance/certification.py",
    "src/fastapi_effects/conformance/cli.py",
    "src/fastapi_effects/conformance/contract.py",
    "src/fastapi_effects/conformance/loading.py",
    "src/fastapi_effects/conformance/manifest.py",
    "src/fastapi_effects/conformance/models.py",
    "src/fastapi_effects/conformance/protocols.py",
    "src/fastapi_effects/conformance/reporters.py",
    "src/fastapi_effects/conformance/runner.py",
    "src/fastapi_effects/conformance/safety.py",
    "src/fastapi_effects/conformance/scenarios.py",
    "src/fastapi_effects/conformance/spec/boundary-contract-v1.json",
    "src/fastapi_effects/conformance/spec/manifest-v1.schema.json",
    "src/fastapi_effects/conformance/spec/report-v1.schema.json",
    "src/fastapi_effects/testing/assertions.py",
    "src/fastapi_effects/testing/reference.py",
    "tests/conformance/test_contract_models.py",
    "tests/conformance/test_fault_detection.py",
    "tests/conformance/test_reporters.py",
    "tests/conformance/test_runner_reference.py",
    "tests/security/test_conformance_redaction.py",
    "docs/concepts/conformance.md",
    "docs/operations/certification.md",
    "docs/reference/conformance-api.md",
    "docs/adr/0006-conformance-evidence.md",
    ".github/workflows/conformance.yml",
}
_ACTION_PIN = re.compile(r"uses:\s*[^\s@]+@[0-9a-f]{40}(?:\s*#.*)?$")
_BRANCH = re.compile(
    r"^(main|(?:build|chore|ci|docs|feat|fix|refactor|test)/"
    r"[a-z0-9][a-z0-9-]{1,63})$"
)


@dataclass(slots=True)
class Gate:
    name: str
    required: bool
    status: str = "NOT_RUN"
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "required": self.required,
            "status": self.status,
            "detail": self.detail,
        }


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.rstrip()


def check_paths() -> str:
    missing = sorted(path for path in REQUIRED_PATHS if not (ROOT / path).is_file())
    if missing:
        raise AssertionError(f"missing required paths: {missing}")
    return f"{len(REQUIRED_PATHS)} required files present"


def check_metadata() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project: dict[str, Any] = tomllib.load(stream)
    metadata = project["project"]
    if metadata["name"] != "fastapi-effects":
        raise AssertionError("distribution name changed")
    if metadata.get("authors") != [{"name": PROJECT_AUTHOR}]:
        raise AssertionError("project author must be Zsolt Döme only")
    match = re.match(r"^\d+\.\d+\.\d+", __version__)
    if match is None or tuple(int(item) for item in match.group().split(".")) < MINIMUM_RELEASE:
        raise AssertionError(f"version is {__version__}, expected M7 or later")
    package_data = project["tool"]["setuptools"]["package-data"]["fastapi_effects"]
    if "conformance/spec/*.json" not in package_data:
        raise AssertionError("conformance specifications are not packaged")
    return f"distribution metadata and version {__version__} are valid"


def check_specifications() -> str:
    spec_root = ROOT / "src" / "fastapi_effects" / "conformance" / "spec"
    contract = json.loads((spec_root / "boundary-contract-v1.json").read_text())
    manifest_schema = json.loads((spec_root / "manifest-v1.schema.json").read_text())
    report_schema = json.loads((spec_root / "report-v1.schema.json").read_text())

    runtime_capabilities = {item.value for item in Capability}
    runtime_invariants = {item.value for item in Invariant}
    runtime_profiles = {
        profile.value: {item.value for item in PROFILE_INVARIANTS[profile]}
        for profile in CertificationProfile
    }
    if contract["contract_version"] != CONTRACT_VERSION:
        raise AssertionError("packaged contract version differs from runtime")
    if set(contract["capabilities"]) != runtime_capabilities:
        raise AssertionError("packaged capability set differs from runtime")
    if set(contract["invariants"]) != runtime_invariants:
        raise AssertionError("packaged invariant set differs from runtime")
    contract_profiles = {name: set(values) for name, values in contract["profiles"].items()}
    if contract_profiles != runtime_profiles:
        raise AssertionError("packaged certification profiles differ from runtime")

    if manifest_schema.get("type") != "object" or report_schema.get("type") != "object":
        raise AssertionError("machine-readable schemas are not object schemas")
    if manifest_schema.get("additionalProperties") is not False:
        raise AssertionError("manifest schema permits unknown top-level fields")
    if report_schema.get("additionalProperties") is not False:
        raise AssertionError("report schema permits unknown top-level fields")
    manifest_properties = manifest_schema["properties"]
    if set(manifest_properties["capabilities"]["items"]["enum"]) != runtime_capabilities:
        raise AssertionError("manifest capability enumeration differs from runtime")
    if set(manifest_properties["invariants"]["items"]["enum"]) != runtime_invariants:
        raise AssertionError("manifest invariant enumeration differs from runtime")
    report_properties = report_schema["properties"]
    if set(report_properties["profile"]["enum"]) != set(runtime_profiles):
        raise AssertionError("report profile enumeration differs from runtime")
    check_schema = report_schema["$defs"]["check"]
    if set(check_schema["properties"]["invariant"]["enum"]) != runtime_invariants:
        raise AssertionError("report invariant enumeration differs from runtime")
    if check_schema.get("additionalProperties") is not False:
        raise AssertionError("report check schema permits unknown fields")
    return (
        "contract descriptor, profiles, manifest schema, and report schema match "
        "runtime enumerations"
    )


async def reference_evidence() -> tuple[dict[str, ConformanceReport], dict[str, tuple[str, ...]]]:
    reports: dict[str, ConformanceReport] = {}
    for profile in CertificationProfile:
        driver = ReferenceBoundaryDriver()
        report = await ConformanceRunner(RunnerConfiguration(profile=profile)).run(driver)
        if not report.certified or not decide(report).certified:
            raise AssertionError(f"reference driver failed profile {profile.value}")
        loaded = ConformanceReport.from_json(render_report(report, ReportFormat.JSON))
        decision = verify_evidence(loaded, ReferenceBoundaryDriver().manifest)
        if not decision.certified:
            raise AssertionError(f"archived evidence failed profile {profile.value}")
        reports[profile.value] = report

    detected: dict[str, tuple[str, ...]] = {}
    for fault in Fault:
        report = await ConformanceRunner(
            RunnerConfiguration(profile=CertificationProfile.COMPLETE)
        ).run(ReferenceBoundaryDriver(faults=(fault,)))
        failing = tuple(item.check_id for item in report.results if item.status.value != "pass")
        if report.certified or not failing:
            raise AssertionError(f"fault was not detected: {fault.value}")
        detected[fault.value] = failing
    return reports, detected


def check_reference_suite() -> str:
    reports, detected = asyncio.run(reference_evidence())
    complete = reports[CertificationProfile.COMPLETE.value]
    return (
        f"{len(reports)} profiles certified; {len(complete.results)} complete-profile checks; "
        f"{len(detected)} injected faults detected"
    )


def check_reporters() -> str:
    async def build() -> ConformanceReport:
        return await ConformanceRunner(
            RunnerConfiguration(profile=CertificationProfile.COMPLETE)
        ).run(ReferenceBoundaryDriver())

    report = asyncio.run(build())
    json_report = render_report(report, ReportFormat.JSON)
    loaded = ConformanceReport.from_json(json_report)
    if loaded != report:
        raise AssertionError("JSON report round trip changed evidence")
    junit = ET.fromstring(render_report(report, ReportFormat.JUNIT))
    if junit.tag != "testsuite":
        raise AssertionError("JUnit reporter produced an unexpected root")
    sarif = json.loads(render_report(report, ReportFormat.SARIF))
    if sarif.get("version") != "2.1.0":
        raise AssertionError("SARIF reporter version is invalid")
    markdown = render_report(report, ReportFormat.MARKDOWN)
    if "Certified: **yes**" not in markdown:
        raise AssertionError("Markdown reporter omitted certification decision")
    with tempfile.TemporaryDirectory(prefix="fastapi_effects_m7-report-") as raw:
        destination = write_report(Path(raw) / "report.json", json_report)
        if stat.S_IMODE(destination.stat().st_mode) != 0o600:
            raise AssertionError("written report is not private by default")
    canary = "conformance-secret-canary-reference-key"
    rendered_reports = (
        json_report,
        ET.tostring(junit, encoding="unicode"),
        json.dumps(sarif),
        markdown,
    )
    for rendered in rendered_reports:
        if canary in rendered:
            raise AssertionError("reporter exposed the reference signing canary")
    return "JSON, JUnit, SARIF, Markdown, digest, and private-write gates passed"


def literal_all(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            raise AssertionError(f"{path} __all__ must be a literal sequence")
        return {
            element.value
            for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    raise AssertionError(f"{path} does not define __all__")


def check_public_surface() -> str:
    root_exports = literal_all(ROOT / "src" / "fastapi_effects" / "__init__.py")
    conformance_exports = literal_all(
        ROOT / "src" / "fastapi_effects" / "conformance" / "__init__.py"
    )
    if root_exports & conformance_exports:
        raise AssertionError("Milestone 7 leaked assurance symbols into the root API")
    required = {
        "CapabilityManifest",
        "CertificationProfile",
        "ConformanceRunner",
        "ConformanceReport",
        "verify_evidence",
    }
    if not required.issubset(conformance_exports):
        raise AssertionError("conformance subpackage public API is incomplete")
    return "root API remains narrow and conformance API is explicit"


def check_workflow_pins() -> str:
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    failures: list[str] = []
    action_count = 0
    for workflow in workflows:
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            if "uses:" not in line:
                continue
            action_count += 1
            if not _ACTION_PIN.search(line.strip()):
                failures.append(f"{workflow.name}:{line_number}:{line.strip()}")
    if failures:
        raise AssertionError(f"GitHub Actions are not SHA-pinned: {failures}")
    return f"{action_count} GitHub Action references are SHA-pinned"


def check_git_governance() -> str:
    records = run_git(
        "log",
        "--branches",
        "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%s",
    ).splitlines()
    if not records:
        raise AssertionError("Git history is empty")
    bad_identities: list[str] = []
    bad_subjects: list[str] = []
    for line in records:
        commit, author, author_email, committer, committer_email, subject = line.split("\x00", 5)
        if commit == RECOVERED_BASELINE_COMMIT:
            recovered = (
                author,
                author_email,
                committer,
                committer_email,
                subject,
            )
            expected_recovered = (
                AUTHOR_NAME,
                RECOVERED_BASELINE_EMAIL,
                LEGACY_COMMITTER_NAME,
                RECOVERED_BASELINE_EMAIL,
                ".gitignore",
            )
            if recovered != expected_recovered:
                bad_identities.append(f"{commit[:10]}:recovered baseline changed")
            continue
        if (
            author != AUTHOR_NAME
            or committer not in {AUTHOR_NAME, LEGACY_COMMITTER_NAME}
            or author_email != committer_email
            or not author_email.endswith(AUTHOR_EMAIL_SUFFIX)
        ):
            bad_identities.append(f"{commit[:10]}:{subject}")
        words = subject.split()
        if not 3 <= len(words) <= 7:
            bad_subjects.append(f"{commit[:10]}:{subject}")
    if bad_identities:
        raise AssertionError(f"unexpected Git identities: {bad_identities}")
    if bad_subjects:
        raise AssertionError(f"commit subjects outside 3-7 words: {bad_subjects}")
    branches = run_git("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
    bad_branches = [branch for branch in branches if not _BRANCH.fullmatch(branch)]
    if bad_branches:
        raise AssertionError(f"invalid branch names: {bad_branches}")
    unmerged = [
        branch
        for branch in branches
        if branch != "main"
        and subprocess.run(
            ("git", "merge-base", "--is-ancestor", branch, "main"),
            cwd=ROOT,
            check=False,
            capture_output=True,
        ).returncode
        != 0
    ]
    if unmerged:
        raise AssertionError(f"branches not merged into main: {unmerged}")
    if run_git("status", "--porcelain"):
        raise AssertionError("Git working tree is not clean")
    subprocess.run(("git", "fsck", "--full"), cwd=ROOT, check=True, capture_output=True)
    return (
        f"{len(branches)} local branches, governed identities, clean tree, and Git integrity passed"
    )


def execute_gate(gate: Gate, callback: Callable[[], str]) -> None:
    try:
        gate.detail = callback()
        gate.status = "PASS"
    except Exception as exc:
        gate.status = "FAIL"
        gate.detail = f"{type(exc).__name__}: {exc}"


def render_markdown(gates: list[Gate]) -> str:
    mandatory = all(gate.status == "PASS" for gate in gates if gate.required)
    lines = [
        "# FastAPI Effects Milestone 7 audit",
        "",
        f"**Version:** `{__version__}`  ",
        f"**Overall mandatory result:** {'PASS' if mandatory else 'FAIL'}",
        "",
        "| Gate | Result | Required | Detail |",
        "|---|---:|---:|---|",
    ]
    for gate in gates:
        detail = gate.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{gate.name}` | **{gate.status}** | {'yes' if gate.required else 'no'} | {detail} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-git-governance", action="store_true")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    gates = [
        Gate("required_paths", True),
        Gate("metadata", True),
        Gate("specifications", True),
        Gate("reference_suite", True),
        Gate("reporters", True),
        Gate("public_surface", True),
        Gate("workflow_pins", True),
        Gate("git_governance", not args.skip_git_governance),
    ]
    callbacks: dict[str, Callable[[], str]] = {
        "required_paths": check_paths,
        "metadata": check_metadata,
        "specifications": check_specifications,
        "reference_suite": check_reference_suite,
        "reporters": check_reporters,
        "public_surface": check_public_surface,
        "workflow_pins": check_workflow_pins,
        "git_governance": check_git_governance,
    }
    for gate in gates:
        if gate.name == "git_governance" and args.skip_git_governance:
            gate.status = "NOT_RUN"
            gate.detail = "explicitly skipped"
            continue
        execute_gate(gate, callbacks[gate.name])

    payload = {
        "version": __version__,
        "contract_version": CONTRACT_VERSION,
        "overall": (
            "PASS" if all(gate.status == "PASS" for gate in gates if gate.required) else "FAIL"
        ),
        "gates": [gate.as_dict() for gate in gates],
    }
    markdown = render_markdown(gates)
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        Path(args.markdown_output).write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0 if payload["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
