"""Bounded broker envelope containing no sessions, credentials, or principal payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError


@dataclass(frozen=True, slots=True)
class TaskiqHandoffEnvelope:
    tenant_id: UUID
    handoff_id: UUID
    delivery_id: UUID
    attempt_id: UUID
    task_id: str
    handoff_token: UUID = field(repr=False)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value in (
            self.tenant_id,
            self.handoff_id,
            self.delivery_id,
            self.attempt_id,
            self.handoff_token,
        ):
            if not isinstance(value, UUID):
                raise MergenConfigurationError("Taskiq handoff identity is invalid.")
        if (
            not isinstance(self.task_id, str)
            or not self.task_id.startswith("mergen-")
            or len(self.task_id) > 128
        ):
            raise MergenConfigurationError("Taskiq task identity is invalid.")
        if self.schema_version != 1:
            raise MergenConfigurationError("Taskiq handoff envelope revision is unsupported.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tenant_id": str(self.tenant_id),
            "handoff_id": str(self.handoff_id),
            "delivery_id": str(self.delivery_id),
            "attempt_id": str(self.attempt_id),
            "task_id": self.task_id,
            "handoff_token": str(self.handoff_token),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> TaskiqHandoffEnvelope:
        expected = {
            "schema_version",
            "tenant_id",
            "handoff_id",
            "delivery_id",
            "attempt_id",
            "task_id",
            "handoff_token",
        }
        if set(value) != expected:
            raise MergenConfigurationError("Taskiq handoff envelope fields are invalid.")
        try:
            schema_version = value["schema_version"]
            task_id = value["task_id"]
            if not isinstance(schema_version, int) or isinstance(schema_version, bool):
                raise TypeError
            if not isinstance(task_id, str):
                raise TypeError
            return cls(
                schema_version=schema_version,
                tenant_id=UUID(_text(value["tenant_id"])),
                handoff_id=UUID(_text(value["handoff_id"])),
                delivery_id=UUID(_text(value["delivery_id"])),
                attempt_id=UUID(_text(value["attempt_id"])),
                task_id=task_id,
                handoff_token=UUID(_text(value["handoff_token"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MergenConfigurationError("Taskiq handoff envelope is invalid.") from exc


def stable_task_id(attempt_id: UUID) -> str:
    if not isinstance(attempt_id, UUID):
        raise MergenConfigurationError("Taskiq attempt identity must be a UUID.")
    return f"mergen-{attempt_id.hex}"


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


__all__ = ["TaskiqHandoffEnvelope", "stable_task_id"]
