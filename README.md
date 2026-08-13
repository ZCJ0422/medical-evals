# Medical LLM Evaluation Framework

`medical-evals` is a medical large-language-model evaluation framework built
on top of the OpenAI Evals execution engine.

## Architecture

```text
medical-evals/
├── medical_evals/                 # Medical-domain extension layer
│   ├── datasets
│   ├── evals
│   ├── metrics
│   ├── graders
│   ├── judges
│   ├── adapters
│   ├── reports
│   ├── models
│   └── human
├── registry/                       # Project-owned configuration registry
│   ├── evals
│   ├── datasets
│   ├── models
│   └── judges
├── experiments/                    # Experiment management
│   ├── configs
│   ├── runs
│   └── snapshots
├── tests/                          # Unit and integration tests
└── docs/                           # Project documentation
```

Directory responsibilities are intentionally separated:

- `evals`: the pinned external OpenAI Evals runtime dependency, including Eval,
  CompletionFn, Recorder, Registry loading, metrics, and the CLI runner. It is
  intentionally not vendored into this repository.
- `medical_evals/`: medical-domain extension layer.
- `registry/`: versioned configuration registration for this project’s
  evaluations, datasets, models, and judges. Pass it to the OpenAI Evals CLI
  with `--registry_path ./registry`.
- `experiments/`: experiment configurations, run records, and snapshots.
- `tests/`: unit, package, adapter, metric, and integration test organization.
- `docs/`: project and framework documentation.

## Development

To get the latest project snapshot without downloading the full Git history:

```bash
git clone --depth 1 https://github.com/ZCJ0422/medical-evals.git
cd medical-evals
```

Use a regular `git clone` instead if you need to inspect the complete commit
history.

Detailed technical documentation:

- [Project technical documentation](docs/project-technical.md)
- [MedQA technical documentation](docs/medqa-technical.md)
- [HealthBench technical documentation](docs/healthbench-technical.md)

## Internal workbench

The first workbench vertical slice lives under `backend/` and `frontend/`. It is
designed for one fixed administrator account and a single-machine internal
deployment. The API and worker boundaries are separate from the existing
evaluation code so the evaluator can later move to a multi-worker deployment.

Initialize the local API database and start the API with:

```bash
cd backend
python -m medical_evals_api.cli init-db
./scripts/run_api.sh
```

The frontend is a separate Next.js application:

```bash
cd frontend
npm install
npm run dev
```

Do not place provider API keys in frontend configuration, browser storage,
Registry files, run JSONL, reports, or logs. Platform benchmark questions,
answers, and complete Rubrics are protected backend data; ordinary result
responses expose only aggregate metrics. The administrator-only raw-sample
route is intentionally separate from the public result summary route.

The project uses `uv` for environment and lockfile management:

```bash
uv sync
uv run pytest
```

The external OpenAI Evals CLI remains available as:

```bash
uv run oaieval --help
```

## Single-sample smoke test

The current CLI accepts the CompletionFn name first and the Eval name second.
For a real OpenAI-compatible endpoint, configure the endpoint through the
environment and run one sample:

```bash
export OPENAI_API_KEY="xxx"
export OPENAI_BASE_URL="https://example.com/v1"
export OPENAI_MODEL="your-model"

uv run oaieval medical-openai-compatible medical-medqa.dev.v1 \
  --registry_path ./registry \
  --max_samples 1 \
  --extra_eval_params temperature=0.1,max_tokens=2048 \
  --local-run \
  --record_path ./experiments/runs/medical-medqa-smoke.jsonl
```

The MedQA Registry defaults are `temperature=0.1` and `max_tokens=2048`.
Override them per run with `--extra_eval_params`, for example
`temperature=0.2,max_tokens=512` for a reasoning model.

When `--record_path` is omitted, the external Evals CLI automatically writes
the result JSONL under `/tmp/evallogs/` using the pattern
`{run_id}_{completion_fn}_{eval}.jsonl`. When `--log_to_file` is omitted, logs
are written to the terminal rather than to an additional `.log` file. Use
`--record_path` and `--log_to_file` when results or logs should be retained
under `experiments/runs/`.

The `medical-openai-compatible` CompletionFn is registered in
`registry/completion_fns/medical_openai_compatible.yaml`. The example
metadata in `configs/medical_medqa_smoke.yaml` documents the dataset, Eval,
model, CompletionFn, and single-sample runner settings.

## HealthBench open-ended smoke test

HealthBench evaluates natural-language medical answers against per-sample
rubrics using a second CompletionFn as a structured judge. The target model
does not receive the rubrics. Run the two-sample smoke set with:

```bash
export OPENAI_API_KEY="xxx"
export OPENAI_BASE_URL="https://example.com/v1"
export OPENAI_MODEL="your-model"

uv run oaieval medical-openai-compatible medical-healthbench.smoke.v1 \
  --registry_path ./registry \
  --max_samples 2 \
  --local-run \
  --record_path ./experiments/runs/healthbench-smoke.jsonl
```

The main, hard, and consensus datasets are available as
`medical-healthbench.oss.v1`, `medical-healthbench.hard.v1`, and
`medical-healthbench.consensus.v1`. Their full JSONL files live under
`../dataset/HealthBench/` in the repository workspace. The judge adapter is
configured through `judge_completion_fn` and defaults to the same registered
OpenAI-compatible adapter in the Registry.

## Model integration strategy

All model and system calls are exposed to evaluations through the external
`CompletionFn` protocol. Evaluation tasks do not call a provider SDK directly.
This keeps the evaluation layer independent from any single model vendor.

Planned integration modes include:

1. OpenAI SDK.
2. OpenAI-compatible APIs, including provider endpoints and self-hosted
   inference servers.
3. Native provider SDKs.
4. Direct HTTP/REST APIs.
5. Local model inference services.
6. Model gateways and routing layers.
7. Agent, RAG, and tool-using medical systems.

The intended boundary is:

```text
Medical Eval
    ↓
CompletionFn
    ↓
Provider, local model, gateway, or agent adapter
```

Future adapters will live under `medical_evals/adapters/`, while the pinned
external `evals` package remains responsible for the CompletionFn protocol,
scheduling, recording, Registry, and CLI execution. The dependency is pinned to
an OpenAI Evals commit in `pyproject.toml` for reproducible installs.

## Roadmap

- **Phase 0:** Repository and package boundary initialization.
- **Phase 1:** MedQA migration and an OpenAI-compatible CompletionFn adapter.
- **Phase 2:** Medical metrics and grading, plus native provider SDK, local
  model, and model-gateway adapters.
- **Phase 3:** Expert evaluation, production-model evaluation, and support for
  Agent/RAG/tool-using medical systems.

## License and provenance

The external OpenAI Evals dependency is distributed under its original MIT
License. This project’s code is distributed under the license in this
repository.
See [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md), and
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
