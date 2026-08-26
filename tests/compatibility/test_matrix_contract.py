from __future__ import annotations

import json
from pathlib import Path

import fastapi
import pydantic
import sqlalchemy

ROOT = Path(__file__).resolve().parents[2]


def test_machine_readable_evidence_identifiers_are_unique_and_complete() -> None:
    evidence_path = Path(__file__).with_name("evidence.json")
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_ids = payload["evidence_ids"]
    assert len(evidence_ids) == len(set(evidence_ids))
    assert {f"compat-python-3.{minor}" for minor in range(11, 15)} <= set(evidence_ids)
    assert {"compat-pg16-py311", "compat-pg18-py314"} <= set(evidence_ids)


def test_resolved_framework_lines_are_within_candidate_envelope() -> None:
    assert tuple(int(part) for part in fastapi.__version__.split(".")[:2]) == (0, 141)
    assert int(pydantic.__version__.split(".")[0]) == 2
    assert tuple(int(part) for part in sqlalchemy.__version__.split(".")[:2]) == (2, 0)


def test_historical_local_snapshot_is_bound_and_not_release_authority() -> None:
    snapshot = json.loads(
        (ROOT / "docs/evidence/compatibility-local.json").read_text(encoding="utf-8")
    )
    assert snapshot["evidence_kind"] == "historical-local-snapshot"
    assert snapshot["release_authority"] is False
    assert len(snapshot["binding"]["implementation_commit"]) == 40
    assert len(snapshot["binding"]["lock_sha256"]) == 64
