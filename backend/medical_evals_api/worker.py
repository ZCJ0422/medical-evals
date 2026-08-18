from .evaluator_adapter import EvaluationAdapter, OpenAICompatibleEvaluationAdapter
from .models import EvaluationTask
from .repositories.tasks import TaskRepository
from .schemas.common import TaskProgress, TaskStatus
from .artifacts import ArtifactWriter, artifact_root_for_database


def _safe_error(error: Exception) -> str:
    if isinstance(error, KeyError):
        return "Evaluation failed because the API key configuration is missing"
    return str(error) or error.__class__.__name__


class Worker:
    def __init__(self, repository: TaskRepository, adapter: EvaluationAdapter | None = None):
        self.repository = repository
        self.adapter = adapter or OpenAICompatibleEvaluationAdapter()

    def run_task(self, task_id: str) -> EvaluationTask:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != TaskStatus.QUEUED:
            return task
        artifacts = ArtifactWriter(artifact_root_for_database(self.repository.database_path), task_id)
        artifacts.log("Run started")
        artifacts.log(f"[config] dataset={task.dataset_version_id}")
        artifacts.log(f"[config] target_model={task.target_model_id}")
        artifacts.log(f"[config] judge_model={task.judge_model_id or '-'}")
        artifacts.log(f"[config] max_samples={task.max_samples or 'all'}")
        checkpoint = artifacts.load_checkpoint()
        if checkpoint:
            artifacts.rewrite_samples(list(checkpoint.values()))
            artifacts.log(f"[checkpoint] resumed_samples={len(checkpoint)}")
        setattr(self.adapter, "checkpoint", checkpoint)
        setattr(self.adapter, "on_log", artifacts.log)
        stage = "preparing"

        def update_stage(next_stage: str) -> None:
            nonlocal stage
            stage = next_stage
            current = self.repository.get(task_id)
            if current is not None:
                self.repository.update_progress(task_id, current.progress.model_copy(update={"stage": stage}))

        def update_progress(progress: TaskProgress) -> None:
            self.repository.update_progress(task_id, progress.model_copy(update={"stage": stage}))

        setattr(self.adapter, "on_stage", update_stage)
        if hasattr(self.adapter, "on_sample"):
            def record_sample(sample):
                artifacts.append_sample(sample)
                if sample.get("error"):
                    artifacts.log(f"[sample {int(sample.get('index', 0)) + 1}] failed: {sample['error']}")
                else:
                    artifacts.log(f"[sample {int(sample.get('index', 0)) + 1}] record persisted")
            self.adapter.on_sample = record_sample
        self.repository.set_status(task_id, TaskStatus.RUNNING)
        update_stage("preparing")
        try:
            result = self.adapter.run(task, update_progress, lambda: self.repository.get(task_id).status == TaskStatus.CANCELLED)
        except Exception as error:
            artifacts.log(f"task failed: {_safe_error(error)}")
            update_stage("failed")
            return self.repository.set_status(task_id, TaskStatus.FAILED, _safe_error(error))
        finally:
            for client in (getattr(self.adapter, "target_client", None), getattr(self.adapter, "judge_client", None)):
                close = getattr(client, "close", None)
                if close:
                    close()
        current = self.repository.get(task_id)
        if current is not None and current.status == TaskStatus.CANCELLED:
            return current
        final_stage = "partial_failed" if result.failed_count else "completed"
        final = TaskProgress(completed_count=result.total_count, total_count=result.total_count, progress_percent=100, success_count=result.success_count, failed_count=result.failed_count, retry_count=result.retry_count, stage=final_stage)
        self.repository.update_progress(task_id, final)
        self.repository.save_result(task_id, total_score=result.total_score, dimension_scores=result.dimension_scores or {}, error_categories=result.error_categories or {}, completed_count=result.success_count, failed_count=result.failed_count, retry_count=result.retry_count, accuracy=result.accuracy, parse_success_rate=result.parse_success_rate, request_success_count=result.request_success_count or result.success_count, parse_failed_count=result.parse_failed_count)
        artifacts.write_summary({"task_id": task_id, "total_score": result.total_score, "accuracy": result.accuracy, "parse_success_rate": result.parse_success_rate, "completed_count": result.total_count, "failed_count": result.failed_count, "retry_count": result.retry_count, "request_success_count": result.request_success_count or result.success_count, "parse_failed_count": result.parse_failed_count})
        artifacts.log(f"[summary] completed={result.success_count} failed={result.failed_count} retries={result.retry_count} total_score={result.total_score:.4f}")
        artifacts.log("Run completed")
        return self.repository.set_status(task_id, TaskStatus.PARTIAL_FAILED if result.failed_count else TaskStatus.COMPLETED)
