# Task 2 Report

Date: 2026-08-26
Baseline commit reviewed: `f7b3ca6`

## Scope Completed

- Replaced fixed-admin authentication with database-backed multi-user authentication.
- Added Argon2id password hashing and verification helpers.
- Added short-lived signed JWT access tokens and hashed refresh-token persistence.
- Added `require_user`, kept `require_admin`, and preserved `/api/v1` auth and `/me` route compatibility.
- Added focused tests for register, login, refresh rotation, logout revocation, disabled users, non-admin rejection, per-user `/me`, and `/api/v1` auth compatibility.

## Files Changed

- Modified: `backend/medical_evals_api/auth.py`
- Modified: `backend/medical_evals_api/database.py`
- Modified: `backend/medical_evals_api/routes/auth.py`
- Modified: `backend/medical_evals_api/main.py`
- Replaced module file with package: `backend/medical_evals_api/models.py` -> `backend/medical_evals_api/models/__init__.py`
- Added: `backend/medical_evals_api/models/users.py`
- Added: `backend/medical_evals_api/repositories/users.py`
- Added: `backend/medical_evals_api/schemas/users.py`
- Modified: `backend/tests/test_auth.py`
- Added: `backend/tests/test_user_isolation.py`

## TDD Notes

1. Added failing auth and isolation tests first.
2. Verified the focused suite failed against the fixed-admin implementation.
3. Implemented minimal auth persistence and route changes to satisfy the new cases.
4. Fixed FastAPI dependency wiring so `Session` and settings are injected via `Depends(...)` instead of leaking into request-body schemas.
5. Fixed SQLite refresh-token expiry comparison by normalizing naive datetimes to UTC.

## Verification

Focused test command:

```bash
cd backend && uv run pytest tests/test_auth.py tests/test_user_isolation.py -q
```

Latest result:

```text
11 passed in 4.67s
```

Additional checks:

- `git diff --check` passed.
- Confirmed OpenAPI request bodies for `/api/auth/register` and related auth routes parse directly as the expected models after dependency fix.

## Implementation Notes

- `UserRepository` ensures `users` and `refresh_tokens` tables exist on demand and seeds the legacy fixed admin as a database record for compatibility with existing admin-only route tests and flows.
- Access tokens contain only `sub`, `uid`, `role`, `type`, `iat`, and `exp`.
- Refresh tokens are stored only as HMAC-SHA256 hashes keyed by the JWT secret; plaintext refresh tokens are returned once at issue time.
- `/api/me` and `/api/v1/me` now resolve the current database user and reject disabled accounts.

## Scope Guardrails Kept

- Did not migrate evaluation persistence to SQLAlchemy tables.
- Did not implement model-profile CRUD or user-scoped model resource routes.
- Did not attempt to address the known broader baseline test failures outside the focused auth suite.

## Concerns

- Auth now uses manual HS256 JWT encoding/verification rather than a third-party JWT library to avoid adding dependencies not present in the locked backend environment.
- The legacy fixed admin remains auto-seeded for backward compatibility; later tasks may want an explicit bootstrap or migration policy for production environments.
