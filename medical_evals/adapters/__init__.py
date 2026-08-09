"""Adapters from medical model providers to the evals CompletionFn protocol."""

from .openai_compatible import (
    EmptyCompletionError,
    OpenAICompatibleCompletionFn,
    OpenAICompatibleCompletionResult,
)

__all__ = [
    "EmptyCompletionError",
    "OpenAICompatibleCompletionFn",
    "OpenAICompatibleCompletionResult",
]
