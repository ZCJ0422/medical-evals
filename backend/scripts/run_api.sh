#!/usr/bin/env sh
set -eu
PYTHONPATH="$(dirname "$0")/.." exec python -m medical_evals_api.cli api
