from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

from medical_evals.core.models import CompletionRequest
from medical_evals.core.openai_compatible import EmptyCompletionError, OpenAICompatibleClient


def request():
    return CompletionRequest("question", "model-a", 0.1, 5120)


def response(text="A", *, usage=None):
    if usage is None:
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=1, total_tokens=11)
    return SimpleNamespace(
        model="model-a",
        usage=usage,
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


class FakeCompletions:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


class FakeOpenAIClient:
    def __init__(self, values):
        self.chat = SimpleNamespace(completions=FakeCompletions(values))


def status_error(status_code, message="provider failure"):
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    return APIStatusError(
        message,
        response=httpx.Response(status_code, request=request),
        body=None,
    )


def test_timeout_retries_are_returned_on_the_response():
    fake_openai_client = FakeOpenAIClient([
        APITimeoutError(request=httpx.Request("POST", "https://example.test")),
        response("A"),
    ])
    sleeps = []
    events = []
    client = OpenAICompatibleClient(
        model="model-a",
        client=fake_openai_client,
        sleep_fn=sleeps.append,
    )

    result = client.complete(request(), events.append)

    assert result.text == "A"
    assert result.retry_count == 1
    assert sleeps == [1.0]
    assert [event.kind for event in events] == [
        "request_started",
        "retry",
        "request_started",
        "request_completed",
    ]
    assert fake_openai_client.chat.completions.calls == [
        {
            "model": "model-a",
            "messages": [{"role": "user", "content": "question"}],
            "temperature": 0.1,
            "max_tokens": 5120,
        },
        {
            "model": "model-a",
            "messages": [{"role": "user", "content": "question"}],
            "temperature": 0.1,
            "max_tokens": 5120,
        },
    ]


def test_request_options_are_forwarded_without_optional_generation_defaults():
    fake_openai_client = FakeOpenAIClient([response("A")])
    client = OpenAICompatibleClient(model="model-a", client=fake_openai_client)

    client.complete(
        CompletionRequest(
            "question",
            "model-a",
            options={
                "stop": ["END"],
                "top_p": 0.4,
                "seed": 7,
                "n": 2,
                "response_format": {"type": "json_object"},
                "tools": [{"type": "function", "function": {"name": "lookup"}}],
            },
        )
    )

    assert fake_openai_client.chat.completions.calls == [
        {
            "model": "model-a",
            "messages": [{"role": "user", "content": "question"}],
            "stop": ["END"],
            "top_p": 0.4,
            "seed": 7,
            "n": 2,
            "response_format": {"type": "json_object"},
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
        }
    ]


def test_retry_count_is_not_shared_between_calls():
    fake_openai_client = FakeOpenAIClient([response("A"), response("B")])
    client = OpenAICompatibleClient(model="model-a", client=fake_openai_client)

    assert client.complete(request()).retry_count == 0
    assert client.complete(request()).retry_count == 0


def test_authentication_error_is_not_retried():
    fake_openai_client = FakeOpenAIClient([status_error(401, "secret-key is invalid")])
    sleeps = []
    client = OpenAICompatibleClient(
        model="model-a",
        client=fake_openai_client,
        sleep_fn=sleeps.append,
    )

    with pytest.raises(APIStatusError):
        client.complete(request())

    assert len(fake_openai_client.chat.completions.calls) == 1
    assert sleeps == []


def test_rate_limit_error_retries():
    fake_openai_client = FakeOpenAIClient([status_error(429), response("B")])
    sleeps = []
    client = OpenAICompatibleClient(
        model="model-a",
        client=fake_openai_client,
        sleep_fn=sleeps.append,
    )

    result = client.complete(request())

    assert result.text == "B"
    assert result.retry_count == 1
    assert sleeps == [1.0]


def test_empty_content_uses_the_full_retry_budget():
    fake_openai_client = FakeOpenAIClient([response(" "), response(""), response(None)])
    sleeps = []
    client = OpenAICompatibleClient(
        model="model-a",
        client=fake_openai_client,
        sleep_fn=sleeps.append,
    )

    with pytest.raises(EmptyCompletionError) as caught:
        client.complete(request())

    assert caught.value.retry_count == 2
    assert len(fake_openai_client.chat.completions.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_usage_latency_and_raw_response_are_normalized():
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=1,
        total_tokens=11,
        prompt_tokens_details={"cached_tokens": 4},
    )
    raw_response = response("A", usage=usage)
    client = OpenAICompatibleClient(
        model="model-a",
        client=FakeOpenAIClient([raw_response]),
    )

    result = client.complete(request())

    assert result.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 1,
        "total_tokens": 11,
    }
    assert result.usage_details == {"prompt_tokens_details": {"cached_tokens": 4}}
    assert result.latency >= 0.0
    assert result.raw_response is raw_response


def test_event_messages_never_include_api_key():
    class SecretTimeoutError(RuntimeError):
        is_timeout = True

    api_key = "secret-key"
    fake_openai_client = FakeOpenAIClient([SecretTimeoutError(api_key), response("A")])
    events = []
    client = OpenAICompatibleClient(
        api_key=api_key,
        model="model-a",
        client=fake_openai_client,
        sleep_fn=lambda _: None,
    )

    client.complete(request(), events.append)

    assert all(api_key not in (event.message or "") for event in events)
