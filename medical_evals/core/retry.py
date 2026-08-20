"""Provider-neutral retry classification and backoff policy."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
SAFE_ERROR_CATEGORIES = frozenset(
    {
        "timeout_error",
        "network_error",
        "rate_limit_error",
        "authentication_error",
        "model_or_endpoint_error",
        "request_error",
        "empty_completion",
    }
)


def classify_status_code(status_code: int) -> tuple[str, bool]:
    """Return the normalized category and retry decision for an HTTP status."""
    if status_code == 429:
        return "rate_limit_error", True
    if status_code == 401:
        return "authentication_error", False
    if status_code == 404:
        return "model_or_endpoint_error", False
    if status_code in RETRYABLE_STATUS_CODES:
        return "request_error", True
    return "request_error", False


def _attribute_values(error: BaseException, names: tuple[str, ...]) -> Iterator[Any]:
    for name in names:
        try:
            yield getattr(error, name)
        except AttributeError:
            continue


def _is_flagged(error: BaseException, names: tuple[str, ...]) -> bool:
    return any(value is True for value in _attribute_values(error, names))


def normalize_error_category(category: object) -> str:
    """Return a canonical category suitable for logs and persisted results."""
    if isinstance(category, str) and category in SAFE_ERROR_CATEGORIES:
        return category
    return "request_error"


def status_code_for_error(error: BaseException) -> int | None:
    """Return a valid HTTP status code without serializing provider text."""
    candidates: list[Any] = list(
        _attribute_values(error, ("status_code", "status"))
    )
    response = getattr(error, "response", None)
    if response is not None:
        candidates.extend(
            _attribute_values(response, ("status_code", "status"))
        )
    for candidate in candidates:
        try:
            status_code = int(candidate)
        except (TypeError, ValueError):
            continue
        if 100 <= status_code <= 599:
            return status_code
    return None


def classify_error(error: BaseException) -> tuple[str, bool]:
    """Normalize an arbitrary provider error without importing its SDK.

    Boundary adapters can expose ``is_timeout`` or ``is_network_error`` on
    their exception wrapper. HTTP-like errors can expose ``status_code`` or
    a response carrying one. A normalized ``category``/``retryable`` pair is
    also honored when supplied by an adapter.
    """
    if _is_flagged(error, ("is_timeout", "timeout", "timed_out")):
        return "timeout_error", True
    if _is_flagged(
        error,
        ("is_network_error", "network_error", "is_connection_error", "connection_error"),
    ):
        return "network_error", True

    category = getattr(error, "category", None)
    retryable = getattr(error, "retryable", None)
    if isinstance(category, str) and isinstance(retryable, bool):
        return normalize_error_category(category), retryable

    status_code = status_code_for_error(error)
    if status_code is not None:
        return classify_status_code(status_code)

    if retryable is True:
        return "request_error", True
    return "request_error", False


def is_retryable_error(error: BaseException) -> bool:
    """Return whether an error should consume another request attempt."""
    return classify_error(error)[1]


def retry_delay_seconds(retry_number: int) -> float:
    """Return the one-based exponential delay for a retry."""
    if retry_number < 1:
        raise ValueError("retry_number must be at least 1")
    return float(2 ** (retry_number - 1))
