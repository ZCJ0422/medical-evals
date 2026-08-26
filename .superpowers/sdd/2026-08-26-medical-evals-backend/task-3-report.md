# Task 3 Report

Status: completed

Scope implemented:
- Added user-owned model profile CRUD under `/api/v1/models`.
- Enforced write-only API keys with encrypted-at-rest storage and `has_api_key` public responses.
- Added OpenAI-compatible base URL validation that rejects non-HTTP(S) URLs and embedded credentials.
- Added safe model connection testing with timeout and sanitized provider/network error handling.
- Added ownership filtering, including a concrete cross-user rejection regression test.

Files changed:
- `backend/medical_evals_api/main.py`
- `backend/medical_evals_api/models/__init__.py`
- `backend/medical_evals_api/models/model_profiles.py`
- `backend/medical_evals_api/repositories/model_profiles.py`
- `backend/medical_evals_api/routes/models.py`
- `backend/medical_evals_api/schemas/model_profiles.py`
- `backend/medical_evals_api/services/model_profiles.py`
- `backend/tests/test_model_profiles.py`
- `backend/tests/test_model_security.py`

Verification:
- `uv run pytest tests/test_model_profiles.py tests/test_model_security.py -q`
- Result after initial implementation: `8 passed`

Fix round:
- Added `PATCH` to FastAPI CORS `allow_methods` so browser preflight accepts model-profile updates.
- Added focused regression tests covering browser `PATCH` preflight plus sanitized timeout and network failures in `/api/v1/models/{id}/test`.

Verification:
- `uv run pytest tests/test_model_profiles.py tests/test_model_security.py -q`
- Result after fix round: `11 passed`

Out of scope preserved:
- No evaluation persistence migration.
- No Redis integration changes.
- No worker migration to model-profile-backed evaluation execution.

Concerns:
- `ModelProfileService.resolve_secret()` exists for later worker integration, but Task 3 does not yet switch evaluation execution to use profile IDs.
- Connection testing currently probes the chat completions path with a minimal request and returns only sanitized success/failure, which is intentional for this task slice.
