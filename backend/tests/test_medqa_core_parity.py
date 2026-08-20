from medical_evals.core.medqa import aggregate_medqa, evaluate_medqa_sample
from medical_evals.core.models import (
    CompletionRequest,
    EvaluationEvent,
    MedQASampleResult,
    ModelResponse,
)
from medical_evals_api.evaluator_adapter import (
    OpenAICompatibleEvaluationAdapter,
    deserialize_medqa_record,
    serialize_medqa_result,
)
from medical_evals_api.models import EvaluationTask
from medical_evals_api.schemas.common import TaskProgress, TaskStatus


MEDQA_SAMPLE = {
    "id": "medqa-1",
    "question": "question",
    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
    "answer": "C",
}


def make_task(*, max_samples=None):
    return EvaluationTask(
        task_id="task-1",
        name="parity",
        target_model_id="model-a",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        status=TaskStatus.RUNNING,
        progress=TaskProgress(),
        created_at="2026-08-20T00:00:00+00:00",
        updated_at="2026-08-20T00:00:00+00:00",
        max_samples=max_samples,
    )


class StaticCoreClient:
    def __init__(self, text="C", retry_count=1):
        self.text = text
        self.retry_count = retry_count
        self.requests = []

    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        self.requests.append(request)
        return ModelResponse(text=self.text, retry_count=self.retry_count)


class FailingCoreClient:
    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        error = RuntimeError("connection lost")
        error.category = "network_error"
        error.retryable = True
        on_event(EvaluationEvent("retry", "request", attempt=1, category=error.category))
        on_event(EvaluationEvent("retry", "request", attempt=2, category=error.category))
        raise error


def test_medqa_result_serialization_covers_success_parse_and_request_failure():
    success = evaluate_medqa_sample(
        StaticCoreClient(), MEDQA_SAMPLE, model="model-a"
    )
    parse_failure = evaluate_medqa_sample(
        StaticCoreClient(text="not a choice", retry_count=0),
        MEDQA_SAMPLE,
        model="model-a",
    )
    request_failure = evaluate_medqa_sample(
        FailingCoreClient(), MEDQA_SAMPLE, model="model-a"
    )

    records = [
        serialize_medqa_result(index, MEDQA_SAMPLE, result)
        for index, result in enumerate((success, parse_failure, request_failure))
    ]

    assert records == [
        {
            "index": 0,
            "sample_id": "medqa-1",
            "question": "question",
            "expected": "C",
            "predicted": "C",
            "correct": True,
            "parse_failed": False,
            "raw_output": "C",
            "error": None,
            "error_category": None,
            "retry_count": 1,
        },
        {
            "index": 1,
            "sample_id": "medqa-1",
            "question": "question",
            "expected": "C",
            "predicted": None,
            "correct": False,
            "parse_failed": True,
            "raw_output": "not a choice",
            "error": None,
            "error_category": None,
            "retry_count": 0,
        },
        {
            "index": 2,
            "sample_id": "medqa-1",
            "question": "question",
            "expected": "C",
            "predicted": None,
            "correct": False,
            "parse_failed": False,
            "raw_output": "",
            "error": "request failed: network_error",
            "error_category": "network_error",
            "error_stage": "request",
            "error_status_code": None,
            "error_attempt": 3,
            "retry_count": 2,
        },
    ]
    assert [deserialize_medqa_record(record) for record in records] == [
        success,
        parse_failure,
        request_failure,
    ]


def test_checkpoint_and_new_results_share_the_core_aggregate(monkeypatch):
    samples = [MEDQA_SAMPLE, {**MEDQA_SAMPLE, "id": "medqa-2"}]
    checkpoint_result = MedQASampleResult(
        "medqa-1", "C", None, "not a choice", False, True, 1
    )
    checkpoint = {0: serialize_medqa_result(0, samples[0], checkpoint_result)}
    client = StaticCoreClient(text="C", retry_count=2)
    adapter = OpenAICompatibleEvaluationAdapter(target_client=client)
    adapter.checkpoint = checkpoint
    persisted = []
    progress = []
    adapter.on_sample = persisted.append
    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples", lambda _: samples
    )

    result = adapter.run(make_task(), progress.append, lambda: False)

    assert len(client.requests) == 1
    assert client.requests[0].model == "model-a"
    assert persisted == [result.samples[1]]
    assert result.success_count == 2
    assert result.failed_count == 0
    assert result.retry_count == 3
    assert result.accuracy == 0.5
    assert result.parse_success_rate == 0.5
    assert result.parse_failed_count == 1
    assert progress[-1].retry_count == 3
    assert aggregate_medqa(
        [deserialize_medqa_record(record) for record in result.samples]
    ).total_score == result.total_score


class EventfulCoreClient:
    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        on_event(EvaluationEvent("request_started", "request", attempt=1))
        on_event(
            EvaluationEvent(
                "retry", "request", attempt=1, category="timeout_error"
            )
        )
        on_event(EvaluationEvent("request_started", "request", attempt=2))
        on_event(EvaluationEvent("request_completed", "request", attempt=2))
        return ModelResponse(text="C", retry_count=1)


def test_core_events_keep_workbench_log_prefixes_and_stages(monkeypatch):
    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples",
        lambda _: [MEDQA_SAMPLE],
    )
    adapter = OpenAICompatibleEvaluationAdapter(target_client=EventfulCoreClient())
    logs = []
    stages = []
    adapter.on_log = logs.append
    adapter.on_stage = stages.append

    result = adapter.run(make_task(max_samples=1), lambda _: None, lambda: False)

    assert result.retry_count == 1
    assert logs == [
        "[sample 1/1] started",
        "[target] request started",
        "[retry] sample 1/1 attempt=2 reason=timeout_error",
        "[target] request started",
        "[target] request completed",
        "[sample 1/1] completed",
    ]
    assert stages == ["target_model", "target_model", "target_model", "parsing"]


def test_medqa_max_samples_and_cancellation_remain_serial(monkeypatch):
    samples = [
        {**MEDQA_SAMPLE, "id": "medqa-1"},
        {**MEDQA_SAMPLE, "id": "medqa-2"},
        {**MEDQA_SAMPLE, "id": "medqa-3"},
    ]
    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples", lambda _: samples
    )
    client = StaticCoreClient(retry_count=0)
    adapter = OpenAICompatibleEvaluationAdapter(target_client=client)
    cancellation_checks = 0

    def is_cancelled():
        nonlocal cancellation_checks
        cancellation_checks += 1
        return cancellation_checks > 1

    result = adapter.run(make_task(max_samples=2), lambda _: None, is_cancelled)

    assert result.total_count == 2
    assert len(client.requests) == 1
    assert len(result.samples) == 1
