"""Strict validation for the bounded, non-sensitive production-readiness record."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

READINESS_SCHEMA_VERSION = 2
MANDATORY_PARTNER_EXERCISES = frozenset(
    {
        "backup_restore",
        "conformance",
        "doctor",
        "incident",
        "manual_replay",
        "migration",
        "relay",
        "retention",
        "retry_reconciliation",
        "schema_check",
    }
)
LIVE_DEPLOYMENT_CLASSES = frozenset({"production", "production_like", "live_staging"})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def validate_readiness_record(
    record: Mapping[str, Any],
    *,
    require_candidate: bool,
) -> tuple[str, ...]:
    """Return stable field-level errors without exposing private partner evidence."""

    errors: list[str] = []
    if record.get("schema_version") != READINESS_SCHEMA_VERSION:
        errors.append("schema_version")

    candidate_version = record.get("candidate_version")
    candidate_commit = record.get("candidate_source_commit")
    candidate_digests = _string_list(record.get("candidate_artifact_digests"))
    candidate_digest_values = candidate_digests or []
    selected_capabilities = _string_list(record.get("selected_capabilities"))
    if require_candidate:
        if candidate_version != "1.0.0rc1":
            errors.append("candidate_version")
        if not _valid_commit(candidate_commit):
            errors.append("candidate_source_commit")
        if not candidate_digests or not all(_valid_digest(item) for item in candidate_digests):
            errors.append("candidate_artifact_digests")
        if len(candidate_digest_values) != len(set(candidate_digest_values)):
            errors.append("candidate_artifact_digests_duplicate")
        if (
            not selected_capabilities
            or not all(_valid_identifier(item) for item in selected_capabilities)
            or len(selected_capabilities) > 32
            or len(selected_capabilities) != len(set(selected_capabilities))
        ):
            errors.append("selected_capabilities")
    else:
        if candidate_version is not None:
            errors.append("candidate_version_pre_v1")
        if candidate_commit is not None:
            errors.append("candidate_source_commit_pre_v1")
        if candidate_digests not in ([], None):
            errors.append("candidate_artifact_digests_pre_v1")

    partners = record.get("partners")
    if not isinstance(partners, list):
        errors.append("partners")
        partners = []
    completed: list[Mapping[str, Any]] = []
    for index, value in enumerate(partners):
        if not isinstance(value, Mapping):
            errors.append(f"partners.{index}")
            continue
        status = value.get("status")
        if status not in {"pending", "complete"}:
            errors.append(f"partners.{index}.status")
            continue
        if status == "complete":
            completed.append(value)
            errors.extend(
                _validate_completed_partner(
                    value,
                    index=index,
                    selected_capabilities=selected_capabilities or [],
                )
            )
    _validate_distinct_completed_partners(completed, errors)

    security = record.get("independent_security_review")
    if not isinstance(security, Mapping):
        errors.append("independent_security_review")
    else:
        status = security.get("status")
        if status not in {"pending", "complete"}:
            errors.append("independent_security_review.status")
        if status == "complete":
            if not _valid_digest(security.get("evidence_digest")):
                errors.append("independent_security_review.evidence_digest")
            if security.get("unresolved_critical_or_high") is not False:
                errors.append("independent_security_review.unresolved_critical_or_high")
            if _has_blocking_issues(security.get("issues")):
                errors.append("independent_security_review.issues")
            review_digest = security.get("evidence_digest")
            if isinstance(review_digest, str) and any(
                partner.get("evidence_digest") == review_digest for partner in completed
            ):
                errors.append("independent_security_review.evidence_digest_duplicate")

    observation = record.get("rc_observation")
    if not isinstance(observation, Mapping):
        errors.append("rc_observation")
    else:
        status = observation.get("status")
        if status not in {"not_started", "in_progress", "complete"}:
            errors.append("rc_observation.status")
        if status == "complete":
            started = _aware_datetime(observation.get("started_at"))
            completed_at = _aware_datetime(observation.get("completed_at"))
            if started is None or completed_at is None or completed_at <= started:
                errors.append("rc_observation.interval")
            if observation.get("candidate_version") != candidate_version:
                errors.append("rc_observation.candidate_version")
            if observation.get("candidate_source_commit") != candidate_commit:
                errors.append("rc_observation.candidate_source_commit")
            observed_digests = _string_list(observation.get("candidate_artifact_digests"))
            if observed_digests != candidate_digests:
                errors.append("rc_observation.candidate_artifact_digests")
            blockers = observation.get("release_blockers")
            if not isinstance(blockers, list) or blockers:
                errors.append("rc_observation.release_blockers")
            if observation.get("reset_by_contract_change") is not False:
                errors.append("rc_observation.reset_by_contract_change")

    approval = record.get("approval")
    if not isinstance(approval, Mapping):
        errors.append("approval")
    else:
        decision = approval.get("decision")
        if decision not in {"no-go", "go"}:
            errors.append("approval.decision")
        if decision == "go":
            approvers = _string_list(approval.get("approvers"))
            if (
                approvers is None
                or len(approvers) < 2
                or len(approvers) != len(set(approvers))
                or not all(_valid_identifier(item) for item in approvers)
            ):
                errors.append("approval.approvers")
            decided_at = _aware_datetime(approval.get("decided_at"))
            if decided_at is None:
                errors.append("approval.decided_at")
            if isinstance(observation, Mapping):
                observed_at = _aware_datetime(observation.get("completed_at"))
                if decided_at is not None and observed_at is not None and decided_at < observed_at:
                    errors.append("approval.before_observation")

    return tuple(dict.fromkeys(errors))


def partner_is_complete(
    value: object,
    *,
    selected_capabilities: list[str],
) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") == "complete"
        and not _validate_completed_partner(
            value,
            index=0,
            selected_capabilities=selected_capabilities,
        )
    )


def valid_digest(value: object) -> bool:
    return _valid_digest(value)


def valid_observation_interval(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    started = _aware_datetime(value.get("started_at"))
    completed = _aware_datetime(value.get("completed_at"))
    return started is not None and completed is not None and completed > started


def _validate_completed_partner(
    value: Mapping[str, Any],
    *,
    index: int,
    selected_capabilities: list[str],
) -> list[str]:
    prefix = f"partners.{index}"
    errors: list[str] = []
    for field in ("id", "environment_owner"):
        if not _valid_identifier(value.get(field)):
            errors.append(f"{prefix}.{field}")
    if value.get("deployment_class") not in LIVE_DEPLOYMENT_CLASSES:
        errors.append(f"{prefix}.deployment_class")
    capabilities = _string_list(value.get("capabilities"))
    if (
        capabilities is None
        or len(capabilities) > 64
        or len(capabilities) != len(set(capabilities))
        or not all(_valid_identifier(item) for item in capabilities)
        or not set(selected_capabilities).issubset(capabilities)
    ):
        errors.append(f"{prefix}.capabilities")
    exercises = _string_list(value.get("exercises"))
    if (
        exercises is None
        or len(exercises) > 64
        or len(exercises) != len(set(exercises))
        or not all(_valid_identifier(item) for item in exercises)
        or not MANDATORY_PARTNER_EXERCISES.issubset(exercises)
    ):
        errors.append(f"{prefix}.exercises")
    evidence_ids = _string_list(value.get("evidence_ids"))
    if (
        not evidence_ids
        or len(evidence_ids) > 64
        or len(evidence_ids) != len(set(evidence_ids))
        or not all(_valid_identifier(item) for item in evidence_ids)
    ):
        errors.append(f"{prefix}.evidence_ids")
    if not _valid_digest(value.get("evidence_digest")):
        errors.append(f"{prefix}.evidence_digest")
    if value.get("approved_by_partner") is not True:
        errors.append(f"{prefix}.approved_by_partner")
    if value.get("approved_by_maintainer") is not True:
        errors.append(f"{prefix}.approved_by_maintainer")
    if _has_blocking_issues(value.get("issues")):
        errors.append(f"{prefix}.issues")
    return errors


def _validate_distinct_completed_partners(
    partners: list[Mapping[str, Any]],
    errors: list[str],
) -> None:
    for field in ("id", "environment_owner", "evidence_digest"):
        values = [value.get(field) for value in partners if isinstance(value.get(field), str)]
        if len(values) != len(set(values)):
            errors.append(f"partners.duplicate_{field}")


def _has_blocking_issues(value: object) -> bool:
    if not isinstance(value, list) or len(value) > 100:
        return True
    for issue in value:
        if not isinstance(issue, Mapping):
            return True
        severity = issue.get("severity")
        status = issue.get("status")
        contract_breaking = issue.get("contract_breaking", False)
        if (
            severity not in {"critical", "high", "medium", "low"}
            or status not in {"open", "resolved", "accepted_nonblocking"}
            or not isinstance(contract_breaking, bool)
        ):
            return True
        if status == "open" and (severity in {"critical", "high"} or contract_breaking is True):
            return True
    return False


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return value


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _valid_commit(value: object) -> bool:
    return isinstance(value, str) and _COMMIT.fullmatch(value) is not None


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


__all__ = [
    "LIVE_DEPLOYMENT_CLASSES",
    "MANDATORY_PARTNER_EXERCISES",
    "READINESS_SCHEMA_VERSION",
    "partner_is_complete",
    "valid_digest",
    "valid_observation_interval",
    "validate_readiness_record",
]
