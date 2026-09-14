"""Compatibility matrix for common OpenAI-compatible provider behaviors."""

from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

from medical_evals.core.healthbench import parse_rubric_judgment
from medical_evals.core.models import CompletionRequest
from medical_evals.core.openai_compatible import OpenAICompatibleClient


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def provider_client(outcomes):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(outcomes)))


def completion_response(content="C"):
    return SimpleNamespace(model="provider-model", usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.mark.parametrize(
    "response",
    [
        {"choices": [{"message": {"content": "C"}}]},
        {"choices": [{"message": {"content": [{"type": "output_text", "text": "C"}]}}]},
        {"choices": [{"text": "C"}]},
        completion_response("C"),
    ],
    ids=["dict-chat", "content-parts", "legacy-text", "sdk-object"],
)
def test_openai_compatible_response_shapes(response):
    client = OpenAICompatibleClient(model="provider-model", client=provider_client([response]), max_retries=0)

    result = client.complete(CompletionRequest("question", "provider-model"))

    assert result.text == "C"


@pytest.mark.parametrize(
    "error",
    [
        APITimeoutError(request=httpx.Request("POST", "https://provider.test/v1/chat/completions")),
        APIStatusError("rate limited", response=httpx.Response(429, request=httpx.Request("POST", "https://provider.test")), body=None),
    ],
    ids=["timeout", "rate-limit"],
)
def test_retryable_provider_failures_retry_then_succeed(error):
    fake = provider_client([error, completion_response("A")])
    client = OpenAICompatibleClient(model="provider-model", client=fake, sleep_fn=lambda _: None)

    result = client.complete(CompletionRequest("question", "provider-model"))

    assert result.text == "A"
    assert result.retry_count == 1
    assert fake.chat.completions.calls == 2


def test_partial_failure_and_malformed_judge_output_remain_classifiable():
    assert parse_rubric_judgment('```json\n{"criteria_met": true, "points": 2}\n```')["criteria_met"] is True
    with pytest.raises(ValueError):
        parse_rubric_judgment("provider returned an explanation without JSON")
