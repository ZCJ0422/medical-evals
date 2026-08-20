import json
import os
from collections import Counter

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from evals.base import RunSpec
from evals.record import DummyRecorder

from medical_evals.core.models import CompletionRequest, EvaluationEvent, ModelResponse
from medical_evals.evals.medqa import MedQAEval
from medical_evals_api.evaluator_adapter import OpenAICompatibleEvaluationAdapter
from medical_evals_api.models import EvaluationTask
from medical_evals_api.schemas.common import TaskProgress, TaskStatus


SAMPLES = [
    {
        "id": "success",
        "question": "success question",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "answer": "C",
    },
    {
        "id": "parse-failure",
        "question": "parse question",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "answer": "A",
    },
    {
        "id": "request-failure",
        "question": "request question",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "answer": "B",
    },
]


class NetworkFailure(RuntimeError):
    category = "network_error"
    retryable = True


class DeterministicClient:
    model = "parity-model"

    def __init__(self):
        self.requests = []

    def _complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        self.requests.append(request)
        if "success question" in request.prompt:
            response = ModelResponse(text="C", model=self.model, retry_count=1)
        elif "parse question" in request.prompt:
            response = ModelResponse(text="not a choice", model=self.model)
        else:
            assert "request question" in request.prompt
            response = NetworkFailure("connection lost")
        if isinstance(response, Exception):
            if on_event is not None:
                on_event(
                    EvaluationEvent(
                        "retry", "request", attempt=1, category=response.category
                    )
                )
                on_event(
                    EvaluationEvent(
                        "request_failed",
                        "request",
                        attempt=2,
                        category=response.category,
                    )
                )
            raise response
        return response

    def complete(self, request, on_event=None):
        return self._complete(request, on_event)

    def complete_core(self, request, on_event=None):
        return self._complete(request, on_event)

    def __call__(self, prompt, **kwargs):
        raise AssertionError("the CLI must use the shared completion protocol")


def make_recorder():
    return DummyRecorder(
        run_spec=RunSpec(
            completion_fns=["deterministic"],
            eval_name="medical-medqa.dev.v1",
            base_eval="medical-medqa",
            split="dev",
            run_config={},
            created_by="parity-test",
        ),
        log=False,
    )


def make_workbench_task():
    return EvaluationTask(
        task_id="parity-task",
        name="parity",
        target_model_id="parity-model",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        status=TaskStatus.RUNNING,
        progress=TaskProgress(),
        created_at="2026-08-20T00:00:00+00:00",
        updated_at="2026-08-20T00:00:00+00:00",
        max_samples=3,
    )


def test_cli_and_workbench_medqa_have_sample_and_aggregate_parity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    dataset_path = tmp_path / "medqa.jsonl"
    dataset_path.write_text(
        "".join(json.dumps(sample) + "\n" for sample in SAMPLES),
        encoding="utf-8",
    )

    cli_client = DeterministicClient()
    recorder = make_recorder()
    cli_summary = MedQAEval(
        completion_fns=[cli_client],
        eval_registry_path=tmp_path,
        name="medical-medqa.dev.v1",
        samples_jsonl=str(dataset_path),
    ).run(recorder)

    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples", lambda _: SAMPLES
    )
    workbench_client = DeterministicClient()
    workbench_summary = OpenAICompatibleEvaluationAdapter(
        target_client=workbench_client
    ).run(make_workbench_task(), lambda _: None, lambda: False)

    cli_records = [event.data for event in recorder.get_events("match")]
    cli_projection = [
        {
            "expected": record["expected"],
            "predicted": record["picked"],
            "correct": record["correct"],
            "parse_failed": record["parse_failed"],
            "retry_count": record["retry_count"],
            "error_category": record["error_category"],
        }
        for record in cli_records
    ]
    workbench_projection = [
        {
            key: record.get(key)
            for key in (
                "expected",
                "predicted",
                "correct",
                "parse_failed",
                "retry_count",
                "error_category",
            )
        }
        for record in workbench_summary.samples
    ]
    cli_projection.sort(key=lambda record: record["expected"])
    workbench_projection.sort(key=lambda record: record["expected"])

    assert cli_projection == workbench_projection == [
        {
            "expected": "A",
            "predicted": None,
            "correct": False,
            "parse_failed": True,
            "retry_count": 0,
            "error_category": None,
        },
        {
            "expected": "B",
            "predicted": None,
            "correct": False,
            "parse_failed": False,
            "retry_count": 1,
            "error_category": "network_error",
        },
        {
            "expected": "C",
            "predicted": "C",
            "correct": True,
            "parse_failed": False,
            "retry_count": 1,
            "error_category": None,
        },
    ]

    cli_error_categories = Counter(
        record["error_category"]
        for record in cli_records
        if record["error_category"] is not None
    )
    cli_aggregate = {
        "accuracy": cli_summary["accuracy"],
        "request_success_count": sum(record["error"] is None for record in cli_records),
        "parse_failed_count": sum(record["parse_failed"] for record in cli_records),
        "failed_count": cli_summary["failed_count"],
        "retry_count": sum(record["retry_count"] for record in cli_records),
        "error_categories": dict(cli_error_categories),
    }
    workbench_aggregate = {
        "accuracy": workbench_summary.accuracy,
        "request_success_count": workbench_summary.request_success_count,
        "parse_failed_count": workbench_summary.parse_failed_count,
        "failed_count": workbench_summary.failed_count,
        "retry_count": workbench_summary.retry_count,
        "error_categories": workbench_summary.error_categories,
    }

    assert cli_aggregate == workbench_aggregate == {
        "accuracy": 1 / 3,
        "request_success_count": 2,
        "parse_failed_count": 1,
        "failed_count": 1,
        "retry_count": 2,
        "error_categories": {"network_error": 1},
    }
    assert len(cli_client.requests) == len(workbench_client.requests) == 3
