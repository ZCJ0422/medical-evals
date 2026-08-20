import httpx
import pytest

from medical_evals.core.models import CompletionRequest, ModelResponse
from medical_evals_api.openai_compatible import OpenAICompatibleClient


def test_openai_compatible_client_returns_chat_content_without_logging_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        seen["model"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "B"}}]})

    client = OpenAICompatibleClient("https://example.test/v1", "secret-key", transport=httpx.MockTransport(handler))
    assert client.complete("question", model="qwen-plus", temperature=0.1, max_tokens=10) == "B"
    assert seen["authorization"] == "Bearer secret-key"
    assert '"model":"qwen-plus"' in seen["model"]


def test_openai_compatible_client_ignores_environment_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "direct"}}]})

    client = OpenAICompatibleClient("https://example.test/v1", "secret-key", transport=httpx.MockTransport(handler))
    assert client.complete("question", model="qwen-plus", temperature=0.1, max_tokens=10) == "direct"
    assert seen["url"] == "https://example.test/v1/chat/completions"


def test_openai_compatible_client_reuses_http_connection(monkeypatch):
    created = []
    original = httpx.Client

    class CountingClient(original):
        def __init__(self, *args, **kwargs):
            created.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", CountingClient)
    client = OpenAICompatibleClient("https://example.test/v1", "secret-key", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})))
    client.complete("one", model="model", temperature=0.1, max_tokens=8)
    client.complete("two", model="model", temperature=0.1, max_tokens=8)
    assert len(created) == 1
    client.close()


def test_openai_compatible_client_retries_timeout_then_returns_response():
    calls = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})

    client = OpenAICompatibleClient(
        "https://example.test/v1",
        "secret-key",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        retry_base_seconds=1.0,
        sleep_fn=sleeps.append,
    )

    assert client.complete("question", model="model", temperature=0.1, max_tokens=10) == "A"
    assert len(calls) == 2
    assert sleeps == [1.0]
    assert client.last_retry_count == 1


def test_openai_compatible_client_defaults_to_two_retries():
    calls = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})

    client = OpenAICompatibleClient(
        "https://example.test/v1",
        "secret-key",
        transport=httpx.MockTransport(handler),
        sleep_fn=sleeps.append,
    )

    assert client.complete("question", model="model", temperature=0.1, max_tokens=10) == "A"
    assert len(calls) == 2
    assert sleeps == [1.0]
    assert client.last_retry_count == 1


def test_openai_compatible_client_does_not_retry_non_retryable_http_error():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, request=request, json={"error": "invalid api key"})

    client = OpenAICompatibleClient(
        "https://example.test/v1",
        "secret-key",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        sleep_fn=lambda _: pytest.fail("authentication errors must not be retried"),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.complete("question", model="model", temperature=0.1, max_tokens=10)
    assert len(calls) == 1
    assert client.last_retry_count == 0


def test_backend_wrapper_accepts_core_requests_and_forwards_retry_events():
    calls = []
    events = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, request=request, json={"error": "rate limited"})
        return httpx.Response(200, json={"model": "model", "choices": [{"message": {"content": "A"}}]})

    client = OpenAICompatibleClient(
        "https://example.test/v1",
        "secret-key",
        transport=httpx.MockTransport(handler),
        max_retries=1,
        sleep_fn=lambda _: None,
    )

    result = client.complete(
        CompletionRequest("question", "model", 0.1, 10),
        on_event=events.append,
    )

    assert isinstance(result, ModelResponse)
    assert result.text == "A"
    assert result.retry_count == 1
    assert [event.kind for event in events] == [
        "request_started",
        "retry",
        "request_started",
        "request_completed",
    ]
    assert all("secret-key" not in (event.message or "") for event in events)


@pytest.mark.parametrize(
    "invalid_response",
    [
        pytest.param(lambda: httpx.Response(200, content=b""), id="empty-2xx-body"),
        pytest.param(
            lambda: httpx.Response(200, content=b"not valid json"),
            id="non-json-2xx-body",
        ),
        pytest.param(
            lambda: httpx.Response(200, json={"choices": 7}),
            id="malformed-choices",
        ),
    ],
)
def test_backend_wrapper_retries_2xx_responses_without_a_usable_completion(
    invalid_response,
):
    calls = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return invalid_response()
        return httpx.Response(
            200,
            json={"model": "model", "choices": [{"message": {"content": "A"}}]},
        )

    client = OpenAICompatibleClient(
        "https://example.test/v1",
        "secret-key",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        retry_base_seconds=1.0,
        sleep_fn=sleeps.append,
    )

    result = client.complete(CompletionRequest("question", "model", 0.1, 10))

    assert isinstance(result, ModelResponse)
    assert result.text == "A"
    assert result.retry_count == 2
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]
