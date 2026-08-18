from fastapi.testclient import TestClient

from medical_evals_api.auth import create_access_token
from medical_evals_api.main import app


def test_catalog_lists_medqa_and_healthbench_without_raw_content():
    client = TestClient(app)
    response = client.get("/api/datasets", headers={"Authorization": f"Bearer {create_access_token('admin')}"})

    assert response.status_code == 200
    payload = response.json()
    ids = {item["dataset_id"] for item in payload}
    assert {"medical-medqa", "medical-healthbench"}.issubset(ids)
    assert all("prompt" not in item and "rubrics" not in item for item in payload)
