import os

import pytest


@pytest.mark.integration
def test_backend_integration_requires_disposable_postgres_and_redis():
    if not os.getenv("MEDICAL_EVALS_TEST_POSTGRES_URL") or not os.getenv("MEDICAL_EVALS_TEST_REDIS_URL"):
        pytest.skip("requires MEDICAL_EVALS_TEST_POSTGRES_URL and MEDICAL_EVALS_TEST_REDIS_URL")
    pytest.fail("disposable-service integration harness is not enabled in this environment")
