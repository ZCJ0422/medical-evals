import json

from medical_evals_api.evaluator_adapter import OpenAICompatibleEvaluationAdapter
from medical_evals_api.artifacts import ArtifactWriter
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.worker import Worker


class FakeClient:
    def complete(self, prompt, *, model, temperature, max_tokens):
        if isinstance(prompt, list) and prompt[0].get("role") == "system":
            return '{"criteria_met": true, "explanation": "meets criterion"}'
        return "A safe answer"


class FailingTargetClient:
    def complete(self, prompt, *, model, temperature, max_tokens):
        raise RuntimeError("401 Client Error: Unauthorized")


class FlakyTargetClient:
    def __init__(self):
        self.calls = 0

    def complete(self, prompt, *, model, temperature, max_tokens):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary target failure")
        return "A safe answer"


class CountingTargetClient(FakeClient):
    def __init__(self):
        self.calls = 0

    def complete(self, prompt, *, model, temperature, max_tokens):
        self.calls += 1
        return super().complete(prompt, model=model, temperature=temperature, max_tokens=max_tokens)


class BudgetRecordingJudgeClient(FakeClient):
    def __init__(self):
        self.max_tokens_seen = []

    def complete(self, prompt, *, model, temperature, max_tokens):
        self.max_tokens_seen.append(max_tokens)
        return '<think>reasoning</think>\n{"criteria_met": true, "explanation": "meets criterion"}'


class FlakyJudgeClient(FakeClient):
    def __init__(self):
        self.calls = 0

    def complete(self, prompt, *, model, temperature, max_tokens):
        self.calls += 1
        if self.calls == 1:
            return ""
        return '{"criteria_met": true, "explanation": "meets criterion"}'


def test_worker_runs_healthbench_with_target_and_judge_clients(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health smoke", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=FakeClient(), judge_client=FakeClient())).run_task(task.task_id)
    assert result.status == TaskStatus.COMPLETED
    assert result.progress.total_count == 2
    saved = repo.get_result(task.task_id)
    assert saved["total_score"] == 0.5
    assert saved["dimension_scores"] == {
        "rubric_score": 0.5,
        "tag:accuracy": 1.0,
        "tag:communication": 1.0,
        "tag:safety": 0.5,
    }


def test_healthbench_worker_appends_increasing_indices_without_atomic_rewrite(
    tmp_path, monkeypatch
):
    def fail_atomic_rewrite(*_args, **_kwargs):
        raise AssertionError("strictly increasing samples must use append persistence")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ArtifactWriter, "_write_samples_atomically", fail_atomic_rewrite)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="ordered HealthBench persistence",
        target_model_id="target",
        judge_model_id="judge",
        dataset_version_id="medical-healthbench.smoke.v1",
        rubric_id="healthbench-default",
    )

    result = Worker(
        repo,
        adapter=OpenAICompatibleEvaluationAdapter(
            target_client=FakeClient(), judge_client=FakeClient()
        ),
    ).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / task.task_id / "samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["index"] for record in records] == [0, 1]
    assert repo.get_result(task.task_id)["total_score"] == 0.5


def test_healthbench_persists_per_sample_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("medical_evals_api.evaluator_adapter.time.sleep", lambda _: None)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health failure", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=FailingTargetClient(), judge_client=FakeClient())).run_task(task.task_id)

    record = (tmp_path / "artifacts" / task.task_id / "samples.jsonl").read_text(encoding="utf-8")
    log = (tmp_path / "artifacts" / task.task_id / "run.log").read_text(encoding="utf-8")
    assert "401 Client Error: Unauthorized" not in record
    assert '"error_category": "request_error"' in record
    assert "401 Client Error: Unauthorized" not in log
    assert "[sample 1] failed" in log


def test_healthbench_retries_the_complete_sample_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("medical_evals_api.evaluator_adapter.time.sleep", lambda _: None)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health sample retry", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    target = FlakyTargetClient()
    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=target, judge_client=FakeClient())).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    assert target.calls == 3
    assert result.progress.retry_count == 1
    records = (tmp_path / "artifacts" / task.task_id / "samples.jsonl").read_text(encoding="utf-8").splitlines()
    assert '"retry_count": 1' in records[0]


def test_healthbench_resumes_from_successful_sample_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health checkpoint", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    ArtifactWriter(tmp_path / "artifacts", task.task_id).append_sample({
        "index": 0,
        "sample_id": "smoke-1",
        "raw_output": "previous answer",
        "error": None,
        "retry_count": 1,
        "score": 1.0,
        "achieved": 1.0,
        "positive_max": 1.0,
        "tag_scores": {"axis:accuracy": 1.0},
    })
    target = CountingTargetClient()
    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=target, judge_client=FakeClient())).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    assert target.calls == 1
    assert result.progress.retry_count == 1
    records = (tmp_path / "artifacts" / task.task_id / "samples.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(records) == 2


def test_healthbench_gives_judge_enough_output_budget_for_reasoning_models(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health judge budget", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    judge = BudgetRecordingJudgeClient()
    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=FakeClient(), judge_client=judge)).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    assert judge.max_tokens_seen == [5120, 5120, 5120, 5120]


def test_healthbench_run_log_records_events_without_raw_answers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health event log", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default", max_samples=1)
    Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=FakeClient(), judge_client=FakeClient())).run_task(task.task_id)

    log = (tmp_path / "artifacts" / task.task_id / "run.log").read_text(encoding="utf-8")

    assert "[config] dataset=medical-healthbench.smoke.v1" in log
    assert "[sample 1/1] started" in log
    assert "[target] request completed" in log
    assert "[judge] request completed" in log
    assert "[score] sample_score=" in log
    assert "A safe answer" not in log


def test_healthbench_retries_a_malformed_judge_response(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("medical_evals_api.evaluator_adapter.time.sleep", lambda _: None)
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="health judge retry", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    judge = FlakyJudgeClient()
    result = Worker(repo, adapter=OpenAICompatibleEvaluationAdapter(target_client=FakeClient(), judge_client=judge)).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    assert judge.calls == 5
