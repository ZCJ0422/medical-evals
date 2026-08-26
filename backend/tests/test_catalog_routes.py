import pytest
from fastapi.testclient import TestClient

from medical_evals_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    import medical_evals_api.database as database

    monkeypatch.setattr(
        config.settings,
        "database_url",
        f"sqlite+pysqlite:///{tmp_path / 'catalog.sqlite3'}",
    )
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def _issue_token(client: TestClient, username: str = "alice") -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_catalog_lists_only_builtin_definitions_without_raw_content(client):
    token = _issue_token(client)

    response = client.get("/api/v1/datasets", headers=_auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["medqa", "healthbench"]
    assert payload[0]["name"] == "MedQA"
    assert payload[0]["requires_judge"] is False
    assert payload[0]["splits"] == [
        {
            "id": "dev",
            "dataset_version_id": "medical-medqa.dev.v1",
            "version": "v1",
            "sample_count": 3425,
            "default_sample_limit": 3425,
        }
    ]
    assert payload[1]["name"] == "HealthBench"
    assert payload[1]["requires_judge"] is True
    assert [item["id"] for item in payload[1]["splits"]] == [
        "smoke",
        "oss",
        "hard",
        "consensus",
    ]
    assert all("prompt" not in item and "rubrics" not in item for item in payload)


def test_v1_routes_remain_visible_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/auth/register" in paths
    assert "/api/v1/me" in paths
    assert "/api/v1/models" in paths
    assert "/api/v1/datasets" in paths
    assert "/api/v1/evaluations" in paths
    assert "/api/v1/evaluations/{run_id}" in paths
