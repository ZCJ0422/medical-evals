# Medical Evals API

Run locally with `./scripts/run_api.sh` or `./scripts/run_worker.sh`. The API
uses PostgreSQL and Redis in deployment; run `python -m medical_evals_api.cli
init-db` before starting services. `/healthz` is liveness, while `/readyz`
checks PostgreSQL readiness. See `../deploy/README.md` for the single-server
Compose deployment.
