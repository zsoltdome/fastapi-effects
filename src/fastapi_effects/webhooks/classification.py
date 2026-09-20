"""Deterministic HTTP outcome and bounded Retry-After classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import StrEnum


class ResponseDisposition(StrEnum):
    SUCCESS = "success"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class ResponseClassification:
    disposition: ResponseDisposition
    code: str
    retry_after: timedelta | None = None


def classify_response(
    status_code: int,
    headers: Mapping[str, str],
    *,
    now: datetime,
    maximum_retry_after: timedelta,
    deadline: datetime | None = None,
) -> ResponseClassification:
    if 200 <= status_code < 300:
        return ResponseClassification(ResponseDisposition.SUCCESS, "webhook.succeeded")
    if status_code in {408, 425, 429} or 500 <= status_code < 600:
        return ResponseClassification(
            ResponseDisposition.RETRYABLE,
            f"webhook.http_{status_code}",
            retry_after=parse_retry_after(
                headers.get("retry-after"),
                now=now,
                maximum=maximum_retry_after,
                deadline=deadline,
            ),
        )
    if 300 <= status_code < 400:
        return ResponseClassification(ResponseDisposition.PERMANENT, "webhook.redirect")
    return ResponseClassification(
        ResponseDisposition.PERMANENT,
        f"webhook.http_{status_code}",
    )


def parse_retry_after(
    value: str | None,
    *,
    now: datetime,
    maximum: timedelta,
    deadline: datetime | None = None,
) -> timedelta | None:
    if value is None or maximum < timedelta(0):
        return None
    normalized = value.strip()
    delay: timedelta
    if normalized.isdigit():
        delay = timedelta(seconds=int(normalized))
    else:
        try:
            parsed = parsedate_to_datetime(normalized)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        delay = parsed - now
    delay = max(timedelta(0), min(delay, maximum))
    if deadline is not None:
        delay = min(delay, max(timedelta(0), deadline - now))
    return delay


__all__ = [
    "ResponseClassification",
    "ResponseDisposition",
    "classify_response",
    "parse_retry_after",
]
