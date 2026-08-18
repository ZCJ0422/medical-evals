from medical_evals_api.evaluator_adapter import OpenAICompatibleEvaluationAdapter
from medical_evals_api.models import EvaluationTask
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.worker import Worker


class FakeClient:
    def complete(self, prompt, *, model, temperature, max_tokens):
        assert "医学单项选择题" in prompt
        assert model == "target"
        return "B"


class CorrectAnswerClient:
    def complete(self, prompt, *, model, temperature, max_tokens):
        return "C"


class ThinkingAnswerClient:
    def __init__(self):
        self.max_tokens = []

    def complete(self, prompt, *, model, temperature, max_tokens):
        self.max_tokens.append(max_tokens)
        return "<think>A、B 需要排除，最终判断为 C</think>\nC"


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
