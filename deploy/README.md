# Single-server backend deployment

Copy `backend/.env.example` to `deploy/.env` and set production secrets, including
`MEDICAL_EVALS_JWT_SECRET`, `MEDICAL_EVALS_ENCRYPTION_SECRET`, and an Argon2id
`MEDICAL_EVALS_FIXED_ADMIN_PASSWORD_HASH`. Then run:

```sh
docker compose -f deploy/docker-compose.backend.yml up -d --build
```

The API container runs checked-in Alembic migrations before starting. PostgreSQL,
Redis, and artifacts use named persistent volumes. Provider keys are submitted by
users at runtime and are never copied into the image or Compose file.

`/healthz` is a process liveness check; `/readyz` only reports ready after a
successful PostgreSQL query. Worker liveness is represented by its container health
and Redis/PostgreSQL lease renewal; inspect `docker compose logs worker` for failures.
