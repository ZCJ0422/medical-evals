"""OpenAI-compatible chat completion adapter for the evals CompletionFn API."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from evals.api import CompletionFn, CompletionResult
from evals.prompt.base import OpenAICreateChatPrompt, Prompt
from evals.record import default_recorder


RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


class EmptyCompletionError(ValueError):
    """Raised internally when an API response has no usable message content."""


def _prompt_to_messages(prompt: Any) -> OpenAICreateChatPrompt:
    """Convert an evals prompt into messages accepted by chat.completions.create."""
    formatted_prompt = prompt.to_formatted_prompt() if isinstance(prompt, Prompt) else prompt

    if isinstance(formatted_prompt, str):
        return [{"role": "user", "content": formatted_prompt}]

    if isinstance(formatted_prompt, list) and all(isinstance(message, dict) for message in formatted_prompt):
        return [dict(message) for message in formatted_prompt]

    raise TypeError(
        "OpenAICompatibleCompletionFn expects a string, chat message list, or evals Prompt"
    )


def _extract_completions(response: Any) -> list[str]:
    """Extract non-empty message contents from an OpenAI chat response."""
    choices = getattr(response, "choices", None) or []
    completions: list[str] = []
    for choice in choices:
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if content is not None and str(content).strip():
            completions.append(str(content))
    return completions


USAGE_TOTAL_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _usage_mapping(usage: Any) -> dict[str, Any] | None:
    """Convert an SDK usage object into a plain mapping when possible."""
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


def _serialize_usage(usage: Any) -> dict[str, Any] | None:
    """Keep only numeric aggregate fields compatible with evals token summation."""
    usage_dict = _usage_mapping(usage)
    if usage_dict is None:
        return None
    return {key: usage_dict.get(key) for key in USAGE_TOTAL_KEYS if key in usage_dict}


def _serialize_usage_details(usage: Any) -> dict[str, Any] | None:
    """Preserve provider-specific usage details outside the aggregate usage map."""
    usage_dict = _usage_mapping(usage)
    if usage_dict is None:
        return None
    details = {key: value for key, value in usage_dict.items() if key not in USAGE_TOTAL_KEYS}
    return details or None


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(error, APIStatusError):
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        return status_code in RETRYABLE_STATUS_CODES
    return False


class OpenAICompatibleCompletionResult(CompletionResult):
    """CompletionResult wrapper around an OpenAI chat response."""

    def __init__(self, raw_data: Any, prompt: OpenAICreateChatPrompt, completions: list[str]):
        self.raw_data = raw_data
        self.prompt = prompt
        self._completions = list(completions)

    def get_completions(self) -> list[str]:
        return list(self._completions)


class OpenAICompatibleCompletionFn(CompletionFn):
    """Call an OpenAI-compatible chat API through the evals CompletionFn protocol."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        max_retries: int = 2,
        retry_base_seconds: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        client: Any = None,
        registry: Any = None,
    ) -> None:
        del registry  # Injected by evals.Registry for registered CompletionFns.
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.base_url = base_url if base_url is not None else os.getenv("OPENAI_BASE_URL")
        self.model = model if model is not None else os.getenv("OPENAI_MODEL")
        if not self.model:
            raise ValueError("model is required for OpenAICompatibleCompletionFn")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds must be non-negative")

        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.sleep_fn = sleep_fn

        if client is None:
            client_kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": timeout,
                # Retries are controlled here so Recorder sees one final failure,
                # rather than an SDK retry being hidden inside the request.
                "max_retries": 0,
            }
            if self.base_url is not None:
                client_kwargs["base_url"] = self.base_url
            client = OpenAI(**client_kwargs)
        self.client = client

    def _record_error(self, error: Exception, attempts: int) -> None:
        recorder = default_recorder()
        if recorder is None:
            return
        recorder.record_error(
            "OpenAI-compatible completion failed",
            error,
            model=self.model,
            attempts=attempts,
            status_code=getattr(getattr(error, "response", None), "status_code", None),
        )

    def _record_sampling(
        self,
        prompt: OpenAICreateChatPrompt,
        response: Any,
        completions: list[str],
        latency: float,
        request_metadata: dict[str, Any],
    ) -> None:
        recorder = default_recorder()
        if recorder is None:
            return

        model = getattr(response, "model", None) or self.model
        completion: Any = completions[0] if len(completions) == 1 else completions
        serialized_usage = _serialize_usage(getattr(response, "usage", None))
        usage_details = _serialize_usage_details(getattr(response, "usage", None))
        sampling_data = {
            "prompt": prompt,
            "sampled": completions,
            "completion": completion,
            "model": model,
            "usage": serialized_usage,
            "latency": latency,
            "request_metadata": request_metadata,
        }
        if usage_details is not None:
            sampling_data["usage_details"] = usage_details
        recorder.record_sampling(**sampling_data)

    def __call__(self, prompt: Any, **kwargs: Any) -> OpenAICompatibleCompletionResult:
        messages = _prompt_to_messages(prompt)
        request_kwargs = dict(kwargs)
        request_kwargs["model"] = self.model
        request_kwargs["messages"] = messages
        request_metadata = {
            key: value for key, value in request_kwargs.items() if key not in {"model", "messages"}
        }

        response = None
        started_at = time.perf_counter()
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(**request_kwargs)
                completions = _extract_completions(response)
                if not completions:
                    raise EmptyCompletionError(
                        "OpenAI-compatible response has no choices or message content"
                    )

                self._record_sampling(
                    messages,
                    response,
                    completions,
                    latency=time.perf_counter() - started_at,
                    request_metadata=request_metadata,
                )
                return OpenAICompatibleCompletionResult(response, messages, completions)
            except EmptyCompletionError as error:
                if attempt < self.max_retries:
                    self.sleep_fn(self.retry_base_seconds * (2**attempt))
                    continue
                self._record_error(error, attempt + 1)
                return OpenAICompatibleCompletionResult(response, messages, [])
            except Exception as error:
                if _is_retryable_error(error) and attempt < self.max_retries:
                    self.sleep_fn(self.retry_base_seconds * (2**attempt))
                    continue
                self._record_error(error, attempt + 1)
                raise

        raise RuntimeError("OpenAI-compatible completion failed after retries")
