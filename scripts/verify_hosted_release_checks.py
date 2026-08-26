#!/usr/bin/env python3
"""Require successful hosted compatibility, security, and conformance checks."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable

import httpx

REQUIRED_CHECKS = frozenset(
    {
        "compat-python-3.11",
        "compat-python-3.12",
        "compat-python-3.13",
        "compat-python-3.14",
        "compat-pg16-py311",
        "compat-pg18-py314",
        "compat-min-base",
        "compat-min-webhooks",
        "compat-min-otel",
        "compat-min-taskiq",
        "compat-min-fastmcp",
        "compat-latest-all",
        "Reference assurance suite",
        "Real complete / PostgreSQL 16",
        "Real complete / PostgreSQL 18",
        "audit",
    }
)


def missing_successful_checks(
    runs: Iterable[dict[str, object]],
    *,
    required: frozenset[str] = REQUIRED_CHECKS,
) -> tuple[str, ...]:
    successful = {
        str(run.get("name"))
        for run in runs
        if run.get("status") == "completed" and run.get("conclusion") == "success"
    }
    return tuple(sorted(required - successful))


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Hosted release check verification requires {name}.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA"))
    args = parser.parse_args()
    if not args.repository or not args.commit:
        raise RuntimeError("Hosted release check verification requires repository and commit.")
    api_url = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    response = httpx.get(
        f"{api_url}/repos/{args.repository}/commits/{args.commit}/check-runs",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_required_environment('GITHUB_TOKEN')}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params={"per_page": 100},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    runs = payload.get("check_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise RuntimeError("GitHub check-runs response is malformed.")
    missing = missing_successful_checks(runs)
    if missing:
        print("Missing successful hosted release checks: " + ", ".join(missing))
        return 1
    print(f"Verified {len(REQUIRED_CHECKS)} hosted release checks for {args.commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
