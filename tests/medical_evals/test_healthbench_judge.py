"""Tests for HealthBench rubric judging."""

import json

import pytest

from medical_evals.judges.rubric import (
    RubricJudge,
    build_rubric_judge_prompt,
    parse_rubric_judgment,
)


class PresetCompletionResult:
    def __init__(self, text):
        self.text = text

    def get_completions(self):
        return [self.text]


class PresetCompletionFn:
    def __init__(self, text):
        self.text = text
        self.prompts = []
        self.kwargs = []

    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        return PresetCompletionResult(self.text)


def test_parser_accepts_json_and_markdown_fence():
    assert parse_rubric_judgment('{"criteria_met": true, "explanation": "yes"}') == {
        "criteria_met": True,
        "explanation": "yes",
    }
    assert parse_rubric_judgment(
        '```json\n{"criteria_met": false, "explanation": "no"}\n```'
    )["criteria_met"] is False


def test_parser_rejects_non_boolean_judgment():
    with pytest.raises(ValueError, match="criteria_met"):
        parse_rubric_judgment('{"criteria_met": "true", "explanation": "yes"}')


def test_judge_prompt_contains_context_and_criterion():
    prompt = build_rubric_judge_prompt(
        [{"role": "user", "content": "I have a fever."}],
        "Seek care if severe.",
        "Mentions red flags",
    )
    serialized = json.dumps(prompt, ensure_ascii=False)
    assert "I have a fever." in serialized
    assert "Seek care if severe." in serialized
    assert "Mentions red flags" in serialized
    assert "ideal_completions_data" not in serialized


def test_rubric_judge_forwards_structured_judge_request():
    completion_fn = PresetCompletionFn('{"criteria_met": true, "explanation": "yes"}')
    judge = RubricJudge(completion_fn)

    result = judge.judge(
        [{"role": "user", "content": "I have a fever."}],
        "Seek care if severe.",
        "Mentions red flags",
    )

    assert result["criteria_met"] is True
    assert completion_fn.kwargs == [{"temperature": 0.0, "max_tokens": 5120}]
