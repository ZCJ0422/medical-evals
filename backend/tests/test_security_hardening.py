import ipaddress

import pytest
from fastapi.testclient import TestClient

from medical_evals_api.config import Settings, validate_runtime_security
from medical_evals_api.main import app
from medical_evals_api.security import validate_public_base_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/v1",
        "http://127.0.0.1/v1",
        "http://[::1]/v1",
        "http://192.168.1.10/v1",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.test/v1",
        "https://user:secret@example.test/v1",
    ],
)
def test_public_base_url_rejects_ssrf_targets_and_credentials(url):
    with pytest.raises(ValueError):
        validate_public_base_url(url)


def test_public_base_url_accepts_openai_compatible_https_url():
    assert str(validate_public_base_url("https://api.example.test/v1")).startswith("https://api.example.test")


def test_production_configuration_fails_closed_for_development_secrets():
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        validate_runtime_security(Settings(environment="production"))


def test_request_id_is_returned_and_is_stable_across_error_response():
    with TestClient(app) as client:
        response = client.get("/api/v1/datasets")
    assert response.status_code in {401, 403}
    assert response.headers["X-Request-ID"]
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
