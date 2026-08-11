"""Structured rubric judging for open-ended medical answers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def build_rubric_judge_prompt(
    prompt: list[dict], answer: str, criterion: str
) -> list[dict]:
    """Build a judge prompt for one rubric criterion."""
    conversation = json.dumps(prompt, ensure_ascii=False)
    return [
        {
            "role": "system",
            "content": (
                "You are a strict medical evaluation judge. Determine whether the candidate "
                "answer satisfies the single rubric criterion. Return only a JSON object with "
                "a boolean criteria_met and a concise explanation string."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Conversation: {conversation}\n\n"
                f"Candidate answer:\n{answer}\n\n"
                f"Rubric criterion:\n{criterion}"
            ),
        },
    ]


def parse_rubric_judgment(text: str) -> dict:
    """Parse a judge JSON response, allowing an optional Markdown fence."""
    if not isinstance(text, str):
        raise ValueError("judge response must be a string")
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid judge JSON: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError("judge response must be a JSON object")
    criteria_met = parsed.get("criteria_met")
    if not isinstance(criteria_met, bool):
        raise ValueError("criteria_met must be a boolean")
    explanation = parsed.get("explanation", "")
    if explanation is None:
        explanation = ""
    if not isinstance(explanation, str):
        raise ValueError("explanation must be a string")
    return {"criteria_met": criteria_met, "explanation": explanation}


def resolve_judge_completion_fn(value: Any, registry: Any):
    """Resolve an injected CompletionFn or a Registry CompletionFn name."""
    if isinstance(value, str):
        return registry.make_completion_fn(value)
    if value is None:
        raise ValueError("judge_completion_fn is required when resolving a judge")
    return value


class RubricJudge:
    """Call a CompletionFn and parse one rubric judgment."""

    def __init__(self, completion_fn, *, temperature: float = 0.0, max_tokens: int = 256):
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
