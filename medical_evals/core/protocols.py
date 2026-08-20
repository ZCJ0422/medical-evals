"""Protocols that keep the shared core independent from model providers."""

from collections.abc import Callable
from typing import Protocol

from .models import CompletionRequest, EvaluationEvent, ModelResponse

EventCallback = Callable[[EvaluationEvent], None]


class ModelClient(Protocol):
    def complete(
        self,
        request: CompletionRequest,
        on_event: EventCallback | None = None,
    ) -> ModelResponse: ...
