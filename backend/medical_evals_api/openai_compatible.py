from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx

from medical_evals.core.models import CompletionRequest, EvaluationEvent, ModelResponse
from medical_evals.core.openai_compatible import OpenAICompatibleClient as CoreOpenAICompatibleClient
from medical_evals.core.protocols import EventCallback


class _HTTPXCompletions:
    """Expose the small OpenAI client surface consumed by the shared client."""

    def __init__(self, client: httpx.Client, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url
        self._api_key = api_key

    def create(self, **payload: Any) -> dict[str, Any]:
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as error:
            error.is_timeout = True
            raise
        except httpx.RequestError as error:
            error.is_network_error = True
            raise


class _HTTPXOpenAIClient:
    def __init__(self, client: httpx.Client, base_url: str, api_key: str) -> None:
        self.chat = SimpleNamespace(
            completions=_HTTPXCompletions(client, base_url, api_key)
        )


class OpenAICompatibleClient(CoreOpenAICompatibleClient):
    """Temporary Workbench compatibility wrapper around the shared core client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 60.0,
        transport=None,
        max_retries: int = 2,
        retry_base_seconds: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, Exception], None] | None = None,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        self.transport = transport
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            trust_env=False,
        )
        self.on_retry = on_retry
        self.last_retry_count = 0
        super().__init__(
            api_key=api_key,
            base_url=normalized_base_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
            sleep_fn=sleep_fn,
            client=_HTTPXOpenAIClient(self._client, normalized_base_url, api_key),
        )

    def _complete_shared(
        self,
        request: CompletionRequest,
        on_event: EventCallback | None,
    ) -> ModelResponse:
        retry_count = 0

        def forward_event(event: EvaluationEvent) -> None:
            nonlocal retry_count
            if event.kind == "retry":
                retry_count = event.attempt
                if self.on_retry is not None:
                    self.on_retry(retry_count, RuntimeError(event.category or "request_error"))
            if on_event is not None:
                on_event(event)

        try:
            response = super().complete(request, on_event=forward_event)
        except Exception:
            self.last_retry_count = retry_count
            raise
        self.last_retry_count = response.retry_count
        return response

    def complete(
        self,
        prompt: CompletionRequest | str | list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        on_event: EventCallback | None = None,
    ) -> ModelResponse | str:
        if isinstance(prompt, CompletionRequest):
            return self._complete_shared(prompt, on_event)

        if model is None or temperature is None or max_tokens is None:
            raise TypeError("legacy completion calls require model, temperature, and max_tokens")
        response = self._complete_shared(
            CompletionRequest(prompt, model, temperature, max_tokens),
            on_event,
        )
        return response.text

    def close(self) -> None:
        self._client.close()
