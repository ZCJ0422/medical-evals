"""OpenAI-compatible chat completion adapter for the evals CompletionFn API."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from evals.api import CompletionFn, CompletionResult
from evals.prompt.base import OpenAICreateChatPrompt, Prompt
from evals.record import default_recorder
from medical_evals.core.models import CompletionRequest, EvaluationEvent, ModelResponse
from medical_evals.core.openai_compatible import EmptyCompletionError, OpenAICompatibleClient


REDACTED = "[REDACTED]"
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b(authorization|api[-_ ]?key|access[-_ ]?token|token|secret|password|signature|sig|cookie)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_").replace(" ", "_")
    if normalized in {"authorization", "api_key", "apikey", "token", "secret", "password", "signature", "sig", "cookie", "key"}:
        return True
    return normalized.endswith(("_api_key", "_token", "_secret", "_password", "_signature", "_credential"))


def _sanitize_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc or not parsed.query:
        return value
    query = [
        (key, REDACTED if _is_sensitive_key(key) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _sanitize_text(value: str, secrets: tuple[str, ...]) -> str:
    sanitized = value
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, REDACTED)
    sanitized = re.sub(
        r"https?://[^\s'\"<>]+",
        lambda match: _sanitize_url(match.group(0)),
        sanitized,
    )
    return _SENSITIVE_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}: {REDACTED}", sanitized)


def _sanitize_value(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(key) else _sanitize_value(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item, secrets) for item in value)
    if isinstance(value, str):
        return _sanitize_text(value, secrets)
    return value


def _sanitized_error(error: Exception, secrets: tuple[str, ...]) -> Exception:
    error_type = type(error).__name__
    sanitized_type = type(error_type, (Exception,), {})
    return sanitized_type(_sanitize_text(str(error), secrets))


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
    choices = (
        response.get("choices", [])
        if isinstance(response, Mapping)
        else getattr(response, "choices", None) or []
    )
    completions: list[str] = []
    for choice in choices:
        message = choice.get("message") if isinstance(choice, Mapping) else getattr(choice, "message", None)
        content = message.get("content") if isinstance(message, Mapping) else getattr(message, "content", None)
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


class OpenAICompatibleCompletionResult(CompletionResult):
    """CompletionResult wrapper around an OpenAI chat response."""

    def __init__(
        self,
        raw_data: Any,
        prompt: OpenAICreateChatPrompt,
        completions: list[str],
        *,
        error: Exception | None = None,
        retry_count: int = 0,
    ):
        self.raw_data = raw_data
        self.prompt = prompt
        self.error = error
        self.retry_count = retry_count
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
        self.core_client = OpenAICompatibleClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            timeout=timeout,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
            sleep_fn=sleep_fn,
            client=client,
        )
        self.client = self.core_client.client
        self._request_metadata: ContextVar[dict[str, Any] | None] = ContextVar(
            "openai_compatible_request_metadata",
            default=None,
        )

    def _record_error(self, error: Exception, attempts: int) -> None:
        recorder = default_recorder()
        if recorder is None:
            return
        recorder.record_error(
            "OpenAI-compatible completion failed",
            _sanitized_error(error, (self.api_key or "",)),
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
            "request_metadata": _sanitize_value(
                request_metadata,
                (self.api_key or "",),
            ),
        }
        if usage_details is not None:
            sampling_data["usage_details"] = usage_details
        recorder.record_sampling(**sampling_data)

    def __call__(self, prompt: Any, **kwargs: Any) -> OpenAICompatibleCompletionResult:
        messages = _prompt_to_messages(prompt)
        request_metadata = {
            key: value for key, value in kwargs.items() if key not in {"model", "messages"}
        }
        request_options = {
            key: value
            for key, value in kwargs.items()
            if key not in {"model", "messages", "temperature", "max_tokens"}
        }
        request = CompletionRequest(
            prompt=messages,
            model=self.model,
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens"),
            options=request_options,
        )
        token = self._request_metadata.set(request_metadata)
        try:
            try:
                response = self.complete_core(request)
            except EmptyCompletionError as error:
                return OpenAICompatibleCompletionResult(
                    error.raw_response,
                    messages,
                    [],
                    error=error,
                    retry_count=error.retry_count,
                )
        finally:
            self._request_metadata.reset(token)

        completions = _extract_completions(response.raw_response) or [response.text]
        return OpenAICompatibleCompletionResult(
            response.raw_response,
            messages,
            completions,
            retry_count=response.retry_count,
        )

    def complete_core(
        self,
        request: CompletionRequest,
        on_event: Callable[[EvaluationEvent], None] | None = None,
    ) -> ModelResponse:
        """Delegate one core request while preserving Recorder side effects."""
        retry_count = 0

        def forward_event(event: EvaluationEvent) -> None:
            nonlocal retry_count
            if event.kind == "retry":
                retry_count = event.attempt
            if on_event is not None:
                on_event(event)

        try:
            response = self.core_client.complete(request, on_event=forward_event)
        except EmptyCompletionError as error:
            self._record_error(error, error.retry_count + 1)
            raise
        except Exception as error:
            self._record_error(error, retry_count + 1)
            raise

        messages = _prompt_to_messages(request.prompt)
        completions = _extract_completions(response.raw_response) or [response.text]
        self._record_sampling(
            messages,
            response.raw_response,
            completions,
            latency=response.latency,
            request_metadata=self._request_metadata.get() or {},
        )
        return response
