import httpx
import pytest
from fastapi.testclient import TestClient

from medical_evals_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    from medical_evals_api import database

    monkeypatch.setattr(config.settings, "database_url", f"sqlite+pysqlite:///{tmp_path / 'model-profiles.sqlite3'}")
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def _issue_token(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides) -> dict[str, str]:
    payload = {
        "name": "Primary",
        "base_url": "https://example.test/v1",
        "model_name": "gpt-4o-mini",
        "api_key": "sk-test-secret",
    }
    payload.update(overrides)
    return payload


def test_create_model_profile_hides_api_key_and_sets_has_api_key(client):
    token = _issue_token(client, "alice")

    response = client.post("/api/v1/models", headers=_auth(token), json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert "api_key" not in body
    assert body["has_api_key"] is True
    assert body["name"] == "Primary"
    assert body["base_url"] == "https://example.test/v1"
    assert body["model_name"] == "gpt-4o-mini"


def test_model_profile_list_is_scoped_to_current_user(client):
    alice = _issue_token(client, "alice")
    bob = _issue_token(client, "bob")

    created = client.post("/api/v1/models", headers=_auth(alice), json=_payload())
    assert created.status_code == 201

    response = client.get("/api/v1/models", headers=_auth(bob))

    assert response.status_code == 200
    assert response.json() == []


def test_model_profile_rejects_cross_user_access(client):
    alice = _issue_token(client, "alice")
    bob = _issue_token(client, "bob")
    created = client.post("/api/v1/models", headers=_auth(alice), json=_payload())
    assert created.status_code == 201
    profile_id = created.json()["id"]

    response = client.get(f"/api/v1/models/{profile_id}", headers=_auth(bob))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Model profile not found"


def test_model_profile_options_allows_patch_for_browser_preflight(client):
    response = client.options(
        "/api/v1/models/some-profile-id",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_model_profile_update_can_replace_secret_without_returning_it(client):
    token = _issue_token(client, "alice")
    created = client.post("/api/v1/models", headers=_auth(token), json=_payload())
    assert created.status_code == 201
    profile_id = created.json()["id"]

    response = client.patch(
        f"/api/v1/models/{profile_id}",
        headers=_auth(token),
        json={"name": "Secondary", "api_key": "sk-rotated-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Secondary"
    assert "api_key" not in body
    assert body["has_api_key"] is True


def test_model_profile_rejects_invalid_openai_compatible_urls(client):
    token = _issue_token(client, "alice")

    bad_scheme = client.post(
        "/api/v1/models",
        headers=_auth(token),
        json=_payload(base_url="sk-not-a-url"),
    )
    embedded_credentials = client.post(
        "/api/v1/models",
        headers=_auth(token),
        json=_payload(base_url="https://user:pass@example.test/v1"),
    )

    assert bad_scheme.status_code == 422
    assert "Base URL must be a complete http:// or https:// URL" in bad_scheme.text
    assert embedded_credentials.status_code == 422
    assert "Base URL must not include embedded credentials" in embedded_credentials.text


def test_model_profile_connection_test_returns_success_without_persisting_output(client, monkeypatch):
    token = _issue_token(client, "alice")
    created = client.post("/api/v1/models", headers=_auth(token), json=_payload())
    assert created.status_code == 201
    profile_id = created.json()["id"]

    calls = []

    class FakeClient:
        def __init__(self, base_url: str, api_key: str, **_: object) -> None:
            calls.append((base_url, api_key))

        def complete(self, prompt: str, *, model: str, temperature: float, max_tokens: int) -> str:
            assert prompt == "ping"
            assert model == "gpt-4o-mini"
            assert temperature == 0
            assert max_tokens == 1
            return "pong"

        def close(self) -> None:
            return None

    monkeypatch.setattr("medical_evals_api.services.model_profiles.OpenAICompatibleClient", FakeClient)

    response = client.post(f"/api/v1/models/{profile_id}/test", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == [("https://example.test/v1", "sk-test-secret")]


def test_model_profile_connection_test_sanitizes_provider_errors(client, monkeypatch):
    token = _issue_token(client, "alice")
    created = client.post("/api/v1/models", headers=_auth(token), json=_payload())
    assert created.status_code == 201
    profile_id = created.json()["id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            request=request,
            json={"error": {"message": "bad key sk-test-secret", "type": "invalid_request_error"}},
        )

    class FakeClient:
        def __init__(self, base_url: str, api_key: str, **_: object) -> None:
            self._client = httpx.Client(transport=httpx.MockTransport(handler))
            self._base_url = base_url
            self._api_key = api_key

        def complete(self, prompt: str, *, model: str, temperature: float, max_tokens: int) -> str:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"messages": [{"role": "user", "content": prompt}], "model": model, "temperature": temperature, "max_tokens": max_tokens},
            )
            response.raise_for_status()
            return "ok"

        def close(self) -> None:
            self._client.close()

    monkeypatch.setattr("medical_evals_api.services.model_profiles.OpenAICompatibleClient", FakeClient)

    response = client.post(f"/api/v1/models/{profile_id}/test", headers=_auth(token))

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Model provider rejected the connection test"
    assert "sk-test-secret" not in response.text


def test_model_profile_connection_test_sanitizes_timeout_errors(client, monkeypatch):
    token = _issue_token(client, "alice")
    created = client.post("/api/v1/models", headers=_auth(token), json=_payload())
    assert created.status_code == 201
    profile_id = created.json()["id"]

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def complete(self, *_args: object, **_kwargs: object) -> str:
            raise httpx.ReadTimeout("timed out talking to sk-test-secret")

        def close(self) -> None:
            return None

    monkeypatch.setattr("medical_evals_api.services.model_profiles.OpenAICompatibleClient", FakeClient)

    response = client.post(f"/api/v1/models/{profile_id}/test", headers=_auth(token))

    assert response.status_code == 504
    assert response.json()["error"]["message"] == "Model provider timed out during the connection test"
    assert "sk-test-secret" not in response.text


def test_model_profile_connection_test_sanitizes_network_errors(client, monkeypatch):
    token = _issue_token(client, "alice")
    created = client.post("/api/v1/models", headers=_auth(token), json=_payload())
    assert created.status_code == 201
    profile_id = created.json()["id"]

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def complete(self, *_args: object, **_kwargs: object) -> str:
            raise httpx.ConnectError("failed to reach sk-test-secret host")

        def close(self) -> None:
            return None

    monkeypatch.setattr("medical_evals_api.services.model_profiles.OpenAICompatibleClient", FakeClient)

    response = client.post(f"/api/v1/models/{profile_id}/test", headers=_auth(token))

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Model provider could not be reached"
    assert "sk-test-secret" not in response.text
