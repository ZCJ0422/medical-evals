from types import SimpleNamespace

import pytest

from medical_evals.core.retry import (
    classify_error,
    classify_status_code,
    is_retryable_error,
    retry_delay_seconds,
)


def test_retryable_status_codes_and_backoff_are_canonical():
    assert classify_status_code(429) == ("rate_limit_error", True)
    assert classify_status_code(503) == ("request_error", True)
    assert classify_status_code(401) == ("authentication_error", False)
    assert classify_status_code(404) == ("model_or_endpoint_error", False)
    assert retry_delay_seconds(1) == 1.0
    assert retry_delay_seconds(2) == 2.0


@pytest.mark.parametrize("status_code", [408, 409, 429, 500, 502, 503, 504])
def test_canonical_transient_status_codes_are_retryable(status_code):
    _, retryable = classify_status_code(status_code)

    assert retryable is True


def test_classify_error_recognizes_normalized_timeout_and_network_flags():
    timeout = SimpleNamespace(is_timeout=True)
    network = SimpleNamespace(is_network_error=True)

    assert classify_error(timeout) == ("timeout_error", True)
    assert classify_error(network) == ("network_error", True)
    assert is_retryable_error(timeout) is True
    assert is_retryable_error(network) is True


def test_classify_error_uses_nested_status_code_without_provider_imports():
    error = SimpleNamespace(response=SimpleNamespace(status_code=401))

    assert classify_error(error) == ("authentication_error", False)
    assert is_retryable_error(error) is False


def test_normalized_error_pair_precedes_status_code_fallback():
    error = SimpleNamespace(
        status_code=503,
        category="authentication_error",
        retryable=False,
    )

    assert classify_error(error) == ("authentication_error", False)
