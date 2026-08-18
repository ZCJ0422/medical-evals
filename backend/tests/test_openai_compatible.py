import httpx

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
