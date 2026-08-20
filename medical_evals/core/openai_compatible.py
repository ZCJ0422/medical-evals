"""Shared OpenAI-compatible request client with explicit retry behavior."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from .models import CompletionRequest, EvaluationEvent, ModelResponse
from .protocols import EventCallback
from .retry import classify_error, retry_delay_seconds


USAGE_TOTAL_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


class EmptyCompletionError(ValueError):
    """Raised when every permitted response has no usable message content."""

    def __init__(self, message: str, *, retry_count: int, raw_response: Any = None) -> None:
        super().__init__(message)
        self.category = "empty_completion"
        self.retryable = True
        self.retry_count = retry_count
        self.raw_response = raw_response


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _messages(prompt: Any) -> list[dict[str, Any]]:
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    if isinstance(prompt, list) and all(isinstance(message, Mapping) for message in prompt):
        return [dict(message) for message in prompt]
    raise TypeError("OpenAI-compatible requests require a string or chat message list")


def _completion_text(response: Any) -> str | None:
    choices = _field(response, "choices", [])
    if not isinstance(choices, (list, tuple)):
        return None
    for choice in choices:
        message = _field(choice, "message")
        content = _field(message, "content")
        if content is not None and str(content).strip():
            return str(content)
    return None


def _usage_mapping(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        value = usage.model_dump()
    elif hasattr(usage, "to_dict"):
        value = usage.to_dict()
    elif is_dataclass(usage):
        value = asdict(usage)
    elif isinstance(usage, Mapping):
        value = dict(usage)
    elif hasattr(usage, "__dict__"):
        value = dict(vars(usage))
    else:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _serialize_usage(usage: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    usage_mapping = _usage_mapping(usage)
    if usage_mapping is None:
        return None, None
    aggregate = {key: usage_mapping[key] for key in USAGE_TOTAL_KEYS if key in usage_mapping}
    details = {key: value for key, value in usage_mapping.items() if key not in USAGE_TOTAL_KEYS}
    return aggregate or None, details or None


def _classify_provider_error(error: Exception) -> tuple[str, bool]:
    if isinstance(error, APITimeoutError):
        return "timeout_error", True
    if isinstance(error, APIConnectionError):
        return "network_error", True
    if isinstance(error, RateLimitError):
        return "rate_limit_error", True
    return classify_error(error)


class OpenAICompatibleClient:
    """Perform one OpenAI-compatible chat completion with shared retry policy."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_base_seconds: float = 1.0,
        sleep_fn=time.sleep,
        client: Any = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds must be non-negative")

        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.sleep_fn = sleep_fn
        if client is None:
            client_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": timeout,
                "max_retries": 0,
            }
            if base_url is not None:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
        self.client = client

    def _emit(
        self,
        on_event: EventCallback | None,
        *,
        kind: str,
        attempt: int,
        category: str | None = None,
        message: str | None = None,
    ) -> None:
        if on_event is not None:
            on_event(
                EvaluationEvent(
                    kind=kind,
                    stage="request",
                    attempt=attempt,
                    category=category,
                    message=message,
                )
            )

    def complete(
        self,
        request: CompletionRequest,
        on_event: EventCallback | None = None,
    ) -> ModelResponse:
        request_kwargs = {
            "model": request.model,
            "messages": _messages(request.prompt),
        }
        request_kwargs.update(request.options)
        if request.temperature is not None:
            request_kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            request_kwargs["max_tokens"] = request.max_tokens
        retry_count = 0
        started_at = time.perf_counter()
        last_response: Any = None

        while True:
            attempt = retry_count + 1
            self._emit(on_event, kind="request_started", attempt=attempt, message="request started")
            try:
                response = self.client.chat.completions.create(**request_kwargs)
                last_response = response
                text = _completion_text(response)
                if text is None:
                    raise EmptyCompletionError(
                        "OpenAI-compatible response has no choices or message content",
                        retry_count=retry_count,
                        raw_response=response,
                    )
                usage, usage_details = _serialize_usage(_field(response, "usage"))
                self._emit(on_event, kind="request_completed", attempt=attempt, message="request completed")
                return ModelResponse(
                    text=text,
                    model=_field(response, "model") or request.model,
                    usage=usage,
                    usage_details=usage_details,
                    latency=time.perf_counter() - started_at,
                    retry_count=retry_count,
                    raw_response=response,
                )
            except EmptyCompletionError as error:
                category = error.category
                retryable = True
                final_error: Exception = error
            except Exception as error:
                category, retryable = _classify_provider_error(error)
                final_error = error

            if not retryable or retry_count >= self.max_retries:
                if isinstance(final_error, EmptyCompletionError):
                    final_error.retry_count = retry_count
                    final_error.raw_response = last_response
                self._emit(
                    on_event,
                    kind="request_failed",
                    attempt=attempt,
                    category=category,
                    message=f"{category} request failed",
                )
                raise final_error

            retry_count += 1
            self._emit(
                on_event,
                kind="retry",
                attempt=retry_count,
                category=category,
                message=f"retrying {category}",
            )
            self.sleep_fn(self.retry_base_seconds * retry_delay_seconds(retry_count))
