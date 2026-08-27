import json

import httpx

from medical_evals.core.models import CompletionRequest, ModelResponse
from medical_evals_api.artifacts import ArtifactWriter
from medical_evals_api.evaluator_adapter import OpenAICompatibleEvaluationAdapter
from medical_evals_api.models import EvaluationTask
from medical_evals_api.openai_compatible import OpenAICompatibleClient
from medical_evals_api.queue import QueueClaim
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.worker import Worker


class FakeClient:
    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        assert "医学单项选择题" in request.prompt
        assert request.model == "target"
        return ModelResponse(text="B")


class CorrectAnswerClient:
    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        return ModelResponse(text="C")


class ThinkingAnswerClient:
    def __init__(self):
        self.max_tokens = []

    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        self.max_tokens.append(request.max_tokens)
        return ModelResponse(text="<think>A、B 需要排除，最终判断为 C</think>\nC")


class RetryCountingClient:
    def complete(self, request, on_event=None):
        assert isinstance(request, CompletionRequest)
        return ModelResponse(text="C", retry_count=1)


class SensitiveProviderError(RuntimeError):
    status_code = 503


class NeverCalledClient:
    def __init__(self):
        self.calls = 0

    def complete(self, request, on_event=None):
        del request, on_event
        self.calls += 1
        raise AssertionError("a cancellation before the first sample must not call the model")


class CapturingEnvironmentClient:
    instances = []

    def __init__(self, base_url, api_key, **kwargs):
        del kwargs
        self.base_url = base_url
        self.api_key = api_key
        self.__class__.instances.append(self)

    def complete(self, request, on_event=None):
        del request, on_event
        return ModelResponse(text="C")

    def close(self):
        return None


class AckTrackingQueue:
    def __init__(self):
        self.heartbeats = []
        self.acked = []

    def heartbeat(self, claim: QueueClaim) -> None:
        self.heartbeats.append(claim)

    def ack(self, claim: QueueClaim) -> None:
        self.acked.append(claim)


def test_worker_resolves_environment_backed_key_at_client_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_EVALS_TEST_TARGET_KEY", "worker-env-key")
    CapturingEnvironmentClient.instances = []
    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.OpenAICompatibleClient",
        CapturingEnvironmentClient,
    )
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="environment-backed smoke",
        target_model_id="target",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        target_base_url="https://target.test/v1",
        target_api_key_env="MEDICAL_EVALS_TEST_TARGET_KEY",
        max_samples=1,
    )

    result = Worker(repo).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    assert len(CapturingEnvironmentClient.instances) == 1
    client = CapturingEnvironmentClient.instances[0]
    assert client.base_url == "https://target.test/v1"
    assert client.api_key == "worker-env-key"


def test_real_worker_acks_queue_claim_after_durable_completion(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="queue-acked smoke",
        target_model_id="target",
        judge_model_id="judge",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        max_samples=1,
        target_base_url="https://target.test/v1",
        target_api_key_env="TARGET_KEY",
        judge_base_url="https://judge.test/v1",
        judge_api_key_env="JUDGE_KEY",
    )
    repo.claim_next("worker-a", lease_seconds=60)
    queue = AckTrackingQueue()
    claim = QueueClaim(run_id=task.task_id, message_id="1-0", consumer="worker-a")
    worker = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(
            target_client=FakeClient(),
            judge_client=FakeClient(),
        ),
        worker_id="worker-a",
        lease_seconds=60,
    )
    worker.queue = queue

    result = worker.run_task(task.task_id, claim)

    assert result.status == TaskStatus.COMPLETED
    assert queue.heartbeats
    assert queue.acked == [claim]


def test_worker_runs_medqa_with_openai_compatible_adapter(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="real smoke", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default", max_samples=1, target_base_url="https://target.test/v1", target_api_key_env="TARGET_KEY", judge_base_url="https://judge.test/v1", judge_api_key_env="JUDGE_KEY")
    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=FakeClient(), judge_client=FakeClient())).run_task(task.task_id)
    assert result.status == TaskStatus.COMPLETED
    assert result.progress.total_count > 0


def test_medqa_result_records_accuracy_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="scored smoke", target_model_id="target", judge_model_id="", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default", max_samples=1)
    Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=CorrectAnswerClient())).run_task(task.task_id)
    saved = repo.get_result(task.task_id)
    assert saved is not None
    assert saved["dimension_scores"] == {"accuracy": 1.0}
    assert saved["total_score"] == 1.0


def test_medqa_worker_reuses_choice_parser_for_thinking_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="parser smoke", target_model_id="target", judge_model_id="", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default", max_samples=1)
    client = ThinkingAnswerClient()
    Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=client)).run_task(task.task_id)
    saved = repo.get_result(task.task_id)
    assert saved is not None
    assert saved["total_score"] == 1.0
    assert client.max_tokens == [5120]


def test_medqa_worker_persists_client_retry_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="retry count", target_model_id="target", judge_model_id="", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default", max_samples=1)
    client = RetryCountingClient()

    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=client)).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    saved = repo.get_result(task.task_id)
    assert saved is not None
    assert saved["retry_count"] == 1
    records = (tmp_path / "artifacts" / task.task_id / "samples.jsonl").read_text(encoding="utf-8")
    assert '"retry_count": 1' in records


def test_medqa_worker_redacts_provider_secrets_from_artifacts_and_logs(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="redaction",
        target_model_id="target",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        max_samples=1,
    )
    api_key = "redaction-worker-api-key"
    userinfo = "redaction-worker-userinfo"
    provider_body = "redaction-worker-provider-body"
    secrets = (api_key, userinfo, provider_body)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise SensitiveProviderError(
            "Authorization: Bearer redaction-worker-api-key; "
            "url=https://alice:redaction-worker-userinfo@example.test/callback; "
            "provider_body=redaction-worker-provider-body"
        )

    client = OpenAICompatibleClient(
        "https://example.test/v1",
        api_key,
        transport=httpx.MockTransport(handler),
        max_retries=0,
        sleep_fn=lambda _: None,
    )

    result = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(target_client=client),
    ).run_task(task.task_id)

    artifacts = tmp_path / "artifacts" / task.task_id
    samples_text = (artifacts / "samples.jsonl").read_text(encoding="utf-8")
    log_text = (artifacts / "run.log").read_text(encoding="utf-8")
    assert result.status == TaskStatus.PARTIAL_FAILED
    assert all(secret not in samples_text for secret in secrets)
    assert all(secret not in log_text for secret in secrets)
    record = json.loads(samples_text)
    assert record["error"] == "request failed: request_error"
    assert record["error_category"] == "request_error"
    assert record["error_stage"] == "request"
    assert record["error_status_code"] == 503
    assert record["error_attempt"] == 1


def test_medqa_worker_keeps_selected_total_when_cancelled_before_first_sample(
    tmp_path, monkeypatch
):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="cancel before first sample",
        target_model_id="target",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        max_samples=2,
    )
    samples = [
        {
            "id": f"sample-{index}",
            "question": f"question-{index}",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "answer": "C",
        }
        for index in range(3)
    ]

    def load_then_cancel(_):
        repo.set_status(task.task_id, TaskStatus.CANCELLED)
        return samples

    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples", load_then_cancel
    )
    client = NeverCalledClient()

    result = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(target_client=client),
    ).run_task(task.task_id)

    assert result.status == TaskStatus.CANCELLED
    assert result.progress.total_count == 2
    assert result.progress.completed_count == 0
    assert result.progress.progress_percent == 0
    assert result.progress.stage == "preparing"
    assert client.calls == 0


def test_medqa_resume_preserves_checkpoint_progress_when_cancelled_before_first_sample(
    tmp_path, monkeypatch
):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="resume then cancel before first sample",
        target_model_id="target",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        max_samples=2,
    )
    ArtifactWriter(tmp_path / "artifacts", task.task_id).append_sample(
        {
            "index": 0,
            "sample_id": "sample-0",
            "question": "question-0",
            "expected": "C",
            "predicted": "C",
            "correct": True,
            "parse_failed": False,
            "raw_output": "C",
            "error": None,
            "error_category": None,
            "retry_count": 2,
        }
    )
    samples = [
        {
            "id": f"sample-{index}",
            "question": f"question-{index}",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "answer": "C",
        }
        for index in range(2)
    ]

    def load_then_cancel(_):
        repo.set_status(task.task_id, TaskStatus.CANCELLED)
        return samples

    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples", load_then_cancel
    )
    client = NeverCalledClient()

    result = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(target_client=client),
    ).run_task(task.task_id)

    api_records, api_total = repo.get_samples(task.task_id)
    assert result.status == TaskStatus.CANCELLED
    assert result.progress.total_count == 2
    assert result.progress.completed_count == 1
    assert result.progress.progress_percent == 50
    assert result.progress.success_count == 1
    assert result.progress.failed_count == 0
    assert result.progress.retry_count == 2
    assert result.progress.stage == "preparing"
    assert api_total == result.progress.completed_count
    assert [record["index"] for record in api_records] == [0]
    assert api_records[0]["retry_count"] == result.progress.retry_count
    assert client.calls == 0


def test_medqa_worker_appends_increasing_indices_without_atomic_rewrite(
    tmp_path, monkeypatch
):
    def fail_atomic_rewrite(*_args, **_kwargs):
        raise AssertionError("strictly increasing samples must use append persistence")

    monkeypatch.setattr(ArtifactWriter, "_write_samples_atomically", fail_atomic_rewrite)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="ordered MedQA persistence",
        target_model_id="target",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        max_samples=2,
    )

    result = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(target_client=FakeClient()),
    ).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / task.task_id / "samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["index"] for record in records] == [0, 1]


def test_medqa_worker_restores_checkpoint_artifact_and_sample_order_by_index(
    tmp_path, monkeypatch
):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="ordered checkpoint resume",
        target_model_id="target",
        judge_model_id="",
        dataset_version_id="medical-medqa.dev.v1",
        rubric_id="medical-medqa.default",
        max_samples=2,
    )
    samples = [
        {
            "id": f"sample-{index}",
            "question": f"question-{index}",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "answer": "C",
        }
        for index in range(2)
    ]
    writer = ArtifactWriter(tmp_path / "artifacts", task.task_id)
    writer.append_sample(
        {
            "index": 0,
            "sample_id": "sample-0",
            "question": "question-0",
            "expected": "C",
            "predicted": None,
            "correct": False,
            "parse_failed": False,
            "raw_output": "",
            "error": "previous failure",
            "error_category": "request_error",
            "retry_count": 0,
        }
    )
    writer.append_sample(
        {
            "index": 1,
            "sample_id": "sample-1",
            "question": "question-1",
            "expected": "C",
            "predicted": "C",
            "correct": True,
            "parse_failed": False,
            "raw_output": "C",
            "error": None,
            "error_category": None,
            "retry_count": 0,
        }
    )
    monkeypatch.setattr(
        "medical_evals_api.evaluator_adapter.load_medqa_samples", lambda _: samples
    )

    result = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(target_client=CorrectAnswerClient()),
    ).run_task(task.task_id)

    artifact_records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / task.task_id / "samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    api_records, total = repo.get_samples(task.task_id)
    assert result.status == TaskStatus.COMPLETED
    assert [record["index"] for record in artifact_records] == [0, 1]
    assert [record["index"] for record in api_records] == [0, 1]
    assert total == 2
