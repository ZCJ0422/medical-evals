"""Unit tests for the OpenAI-compatible CompletionFn adapter."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from evals.base import RunSpec
from evals.cli.oaieval import add_token_usage_to_result
from evals.record import DummyRecorder
from medical_evals.adapters.openai_compatible import OpenAICompatibleCompletionFn


class FakeChatCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(outcomes))


def response(content="模型答案", *, model="medical-model", usage=None, choices=None):
    if choices is None:
        choices = [SimpleNamespace(message=SimpleNamespace(content=content))]
    return SimpleNamespace(model=model, usage=usage, choices=choices)


def recorder():
    run_spec = RunSpec(
        completion_fns=["preset"],
        eval_name="medical-medqa.dev.v1",
        base_eval="medical-medqa",
        split="dev",
        run_config={},
        created_by="test",
    )
    return DummyRecorder(run_spec=run_spec, log=False)


def test_returns_completion_result_and_sends_chat_request():
    usage = SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6)
    client = FakeClient([response("C", usage=usage)])
    adapter = OpenAICompatibleCompletionFn(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="medical-model",
        timeout=17.5,
        client=client,
        max_retries=0,
    )

    with recorder().as_default_recorder("sample-0") as _:
        result = adapter("请回答问题", temperature=0.2, max_tokens=3)

    assert result.get_completions() == ["C"]
    assert client.chat.completions.calls == [
        {
            "model": "medical-model",
            "messages": [{"role": "user", "content": "请回答问题"}],
            "temperature": 0.2,
            "max_tokens": 3,
        }
    ]


def test_passes_api_key_base_url_and_timeout_to_openai_client():
    with patch("medical_evals.adapters.openai_compatible.OpenAI") as openai_client:
        OpenAICompatibleCompletionFn(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="medical-model",
            timeout=12.0,
            max_retries=3,
        )

    openai_client.assert_called_once_with(
        api_key="test-key",
        base_url="https://example.test/v1",
        timeout=12.0,
        max_retries=0,
    )


def test_records_sampling_with_model_completion_and_usage():
    usage = SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6)
    client = FakeClient([response("C", usage=usage)])
    adapter = OpenAICompatibleCompletionFn(model="medical-model", client=client, max_retries=0)
    test_recorder = recorder()

    with test_recorder.as_default_recorder("sample-0"):
        adapter("题目", temperature=0.0, max_tokens=1)

    events = test_recorder.get_events("sampling")
    assert len(events) == 1
    data = events[0].data
    assert data["prompt"] == [{"role": "user", "content": "题目"}]
    assert data["sampled"] == ["C"]
    assert data["model"] == "medical-model"
    assert data["usage"] == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    assert data["completion"] == "C"
    assert data["request_metadata"] == {"temperature": 0.0, "max_tokens": 1}
    assert isinstance(data["latency"], float)
    assert data["latency"] >= 0


def test_normalizes_nested_usage_for_evals_token_aggregation():
    usage = SimpleNamespace(
        prompt_tokens=264,
        completion_tokens=29,
        total_tokens=293,
        completion_tokens_details={"reasoning_tokens": 25},
        prompt_tokens_details={"cached_tokens": 128},
    )
    client = FakeClient([response("B", usage=usage)])
    adapter = OpenAICompatibleCompletionFn(model="medical-model", client=client, max_retries=0)
    test_recorder = recorder()

    with test_recorder.as_default_recorder("sample-0"):
        adapter("题目")

    sampling_data = test_recorder.get_events("sampling")[0].data
    assert sampling_data["usage"] == {
        "prompt_tokens": 264,
        "completion_tokens": 29,
        "total_tokens": 293,
    }
    assert sampling_data["usage_details"] == {
        "completion_tokens_details": {"reasoning_tokens": 25},
        "prompt_tokens_details": {"cached_tokens": 128},
    }

    result = {}
    add_token_usage_to_result(result, test_recorder)

    assert result == {
        "usage_prompt_tokens": 264,
        "usage_completion_tokens": 29,
        "usage_total_tokens": 293,
    }


def test_empty_choices_return_empty_completion_and_record_error():
    client = FakeClient([response(choices=[])])
    adapter = OpenAICompatibleCompletionFn(model="medical-model", client=client, max_retries=0)
    test_recorder = recorder()

    with test_recorder.as_default_recorder("sample-0"):
        result = adapter("题目")

    assert result.get_completions() == []
    error_events = test_recorder.get_events("error")
    assert len(error_events) == 1
    assert error_events[0].data["type"] == "EmptyCompletionError"


def test_empty_content_is_retried_then_returned():
    client = FakeClient([response("  "), response("B")])
    adapter = OpenAICompatibleCompletionFn(
        model="medical-model",
        client=client,
        max_retries=1,
        retry_base_seconds=0,
        sleep_fn=lambda _: None,
    )

    result = adapter("题目")

    assert result.get_completions() == ["B"]
    assert len(client.chat.completions.calls) == 2


def api_error_cases():
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    return [
        pytest.param(APIConnectionError(request=request), id="connection"),
        pytest.param(APITimeoutError(request), id="timeout"),
        pytest.param(
            RateLimitError(
                "rate limited",
                response=httpx.Response(429, request=request),
                body=None,
            ),
            id="rate-limit",
        ),
        pytest.param(
            APIStatusError(
                "server error",
                response=httpx.Response(503, request=request),
                body=None,
            ),
            id="status",
        ),
    ]


@pytest.mark.parametrize("error", api_error_cases())
def test_api_errors_are_retried_recorded_and_reraised(error):
    client = FakeClient([error, error])
    adapter = OpenAICompatibleCompletionFn(
        model="medical-model",
        client=client,
        max_retries=1,
        retry_base_seconds=0,
        sleep_fn=lambda _: None,
    )
    test_recorder = recorder()

    with test_recorder.as_default_recorder("sample-0"), pytest.raises(type(error)):
        adapter("题目")

    assert len(client.chat.completions.calls) == 2
    error_events = test_recorder.get_events("error")
    assert len(error_events) == 1
    assert error_events[0].data["type"] == type(error).__name__
