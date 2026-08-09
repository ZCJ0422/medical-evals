# Medical LLM Evaluation Framework

`medical-evals` is a medical large-language-model evaluation framework built
on top of the OpenAI Evals execution engine.

## Architecture

```text
medical-evals/
├── evals/                         # General-purpose evaluation engine
│   ├── Eval
│   ├── CompletionFn
│   ├── Recorder
│   ├── Registry
│   ├── CLI Runner
│   └── base metrics
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
├── registry/                       # Configuration registry
│   ├── evals
│   ├── datasets
│   ├── models
│   └── judges
├── experiments/                    # Experiment management
│   ├── configs
│   ├── runs
│   └── snapshots
├── tests/                          # Unit and integration tests
├── scripts/                        # Operational and maintenance scripts
└── docs/                           # Project documentation
```

Directory responsibilities are intentionally separated:

- `evals/`: general-purpose evaluation engine, including Eval, CompletionFn,
  Recorder, Registry loading, metrics, and the CLI runner.
- `medical_evals/`: medical-domain extension layer.
- `registry/`: versioned configuration registration for evaluations, datasets,
  models, and judges. This is separate from `evals/registry/`, which belongs to
  the retained evaluation engine.
- `experiments/`: experiment configurations, run records, and snapshots.
- `tests/`: unit, package, adapter, metric, and integration test organization.
- `scripts/`: future data-processing, benchmarking, and release utilities.
- `docs/`: project and framework documentation.

## Development

The project uses `uv` for environment and lockfile management:

```bash
uv sync
uv run pytest
```

The retained evals CLI remains available as:

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
  --max_samples 1 \
  --extra_eval_params temperature=0.1,max_tokens=2048 \
  --local-run \
  --record_path ./experiments/runs/medical-medqa-smoke.jsonl
```

The MedQA Registry defaults are `temperature=0.1` and `max_tokens=2048`.
Override them per run with `--extra_eval_params`, for example
`temperature=0.2,max_tokens=512` for a reasoning model.

When `--record_path` and `--log_to_file` are omitted, the CLI automatically
writes paired files under `experiments/runs/` using the pattern
`{eval_id}__{model}__{run_id}.jsonl` and `{eval_id}__{model}__{run_id}.log`.

The `medical-openai-compatible` CompletionFn is registered in
`evals/registry/completion_fns/medical_openai_compatible.yaml`. The example
metadata in `configs/medical_medqa_smoke.yaml` documents the dataset, Eval,
model, CompletionFn, and single-sample runner settings.

## Model integration strategy

All model and system calls are exposed to evaluations through the retained
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

Future adapters will live under `medical_evals/adapters/`, while the retained
`evals/` package remains responsible for the CompletionFn protocol, scheduling,
recording, Registry, and CLI execution.

## Roadmap

- **Phase 0:** Repository and package boundary initialization.
- **Phase 1:** MedQA migration and an OpenAI-compatible CompletionFn adapter.
- **Phase 2:** Medical metrics and grading, plus native provider SDK, local
  model, and model-gateway adapters.
- **Phase 3:** Expert evaluation, production-model evaluation, and support for
  Agent/RAG/tool-using medical systems.

## License and provenance

The retained OpenAI Evals code is distributed under the original MIT License.
See [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md), and
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
