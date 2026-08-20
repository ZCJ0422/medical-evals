"""Structured rubric judging for open-ended medical answers."""

from __future__ import annotations

from typing import Any

from medical_evals.core.healthbench import build_rubric_judge_prompt as _build_prompt
from medical_evals.core.healthbench import parse_rubric_judgment as _parse_judgment


def build_rubric_judge_prompt(
    prompt: list[dict], answer: str, criterion: str
) -> list[dict]:
    """Build a judge prompt for one rubric criterion."""
    return _build_prompt(prompt, answer, criterion)


def parse_rubric_judgment(text: str) -> dict:
    """Parse a judge JSON response with optional reasoning or Markdown around it."""
    return _parse_judgment(text)


def resolve_judge_completion_fn(value: Any, registry: Any):
    """Resolve an injected CompletionFn or a Registry CompletionFn name."""
    if isinstance(value, str):
        return registry.make_completion_fn(value)
    if value is None:
        raise ValueError("judge_completion_fn is required when resolving a judge")
    return value


class RubricJudge:
    """Call a CompletionFn and parse one rubric judgment."""

    def __init__(self, completion_fn, *, temperature: float = 0.0, max_tokens: int = 5120):
        self.completion_fn = completion_fn
        self.temperature = temperature
        self.max_tokens = max_tokens

    def judge(self, prompt: list[dict], answer: str, criterion: str) -> dict:
        result = self.completion_fn(
            prompt=build_rubric_judge_prompt(prompt, answer, criterion),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        completions = result.get_completions()
        if not completions:
            raise ValueError("judge returned no completion")
        return parse_rubric_judgment(completions[0])
