from collections.abc import Callable
import time

from .artifacts import ArtifactWriter
from .evaluator_adapter import EvaluationAdapter, OpenAICompatibleEvaluationAdapter
from .evaluator_adapter import healthbench_samples_path
from .models import EvaluationTask
from .paths import registry_data_path
from .queue import QueueClaim, TaskQueue
from .repositories.tasks import TaskRepository
from .schemas.common import TaskProgress, TaskStatus
from medical_evals.models import ModelSpec
from medical_evals.reports import EvalRunMetadata, sha256_file


def _safe_error(error: Exception) -> str:
    if isinstance(error, KeyError):
        return "Evaluation failed because the API key configuration is missing"
    return str(error) or error.__class__.__name__


class Worker:
    def __init__(
        self,
        repository: TaskRepository,
        adapter: EvaluationAdapter | None = None,
        worker_id: str = "",
        lease_seconds: int = 300,
    ):
        self.repository = repository
        self.adapter = adapter or OpenAICompatibleEvaluationAdapter()
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.queue: TaskQueue | None = None

    def _renew_execution_claim(self, task_id: str, queue_claim: QueueClaim | None) -> None:
        if not self.worker_id:
            return
        if not self.repository.renew_lease(task_id, self.worker_id, self.lease_seconds):
            raise RuntimeError("Worker lease lost while updating task progress")
        if queue_claim is not None:
            try:
                if self.queue is not None:
                    self.queue.heartbeat(queue_claim)
            except Exception:
                # PostgreSQL remains authoritative if Redis heartbeat refresh fails.
                pass

    def _acknowledge_terminal_claim(
        self,
        task: EvaluationTask,
        queue_claim: QueueClaim | None,
    ) -> EvaluationTask:
        if queue_claim is not None and task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            try:
                if self.queue is not None:
                    self.queue.ack(queue_claim)
            except Exception:
                pass
        return task

    def _claim_queued_task(self, task_id: str) -> EvaluationTask | None:
        if not self.worker_id:
            return None
        claim_task = getattr(self.repository, "claim", None)
        if claim_task is None:
            return None
        return claim_task(task_id, self.worker_id, self.lease_seconds)

    def run_task(
        self,
        task_id: str,
        queue_claim: QueueClaim | None = None,
    ) -> EvaluationTask:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            return self._acknowledge_terminal_claim(task, queue_claim)
        if task.status == TaskStatus.QUEUED:
            claimed = self._claim_queued_task(task_id)
            if claimed is not None:
                task = claimed
            elif self.worker_id:
                current = self.repository.get(task_id)
                if current is None:
                    raise KeyError(task_id)
                if current.status != TaskStatus.RUNNING:
                    return self._acknowledge_terminal_claim(current, queue_claim)
                task = current
        if self.worker_id and task.status == TaskStatus.RUNNING and task.lease_owner and task.lease_owner != self.worker_id:
            raise RuntimeError("Worker does not own the task lease")
        artifacts = ArtifactWriter(self.repository.artifact_root, task_id)
        artifacts.log("Run started")
        artifacts.log(f"[config] dataset={task.dataset_version_id}")
        artifacts.log(f"[config] target_model={task.target_model_id}")
        artifacts.log(f"[config] judge_model={task.judge_model_id or '-'}")
        artifacts.log(f"[config] max_samples={task.max_samples or 'all'}")
        dataset_path = None
        if task.dataset_version_id.startswith("medical-medqa"):
            dataset_path = registry_data_path("medical_medqa", "dev.jsonl")
        elif task.dataset_version_id.startswith("medical-healthbench"):
            dataset_path = healthbench_samples_path(task.dataset_version_id)
        metadata = EvalRunMetadata(
            eval_id=task.dataset_version_id,
            dataset_version=task.dataset_version_id.rsplit(".", 1)[-1],
            dataset_id=task.dataset_version_id.rsplit(".", 1)[0],
            dataset_sha256=sha256_file(dataset_path) if dataset_path and dataset_path.exists() else None,
            model_spec=ModelSpec(model_id=task.target_model_id, provider="openai-compatible"),
            target_model_spec=ModelSpec(model_id=task.target_model_id, provider="openai-compatible"),
            judge_model_spec=(ModelSpec(model_id=task.judge_model_id, provider="openai-compatible") if task.judge_model_id else None),
            prompt_version=f"{task.dataset_version_id.rsplit('.', 1)[0]}.prompt.v1",
            rubric_version=(f"{task.rubric_id}.v1" if task.rubric_id else None),
            grader_version="healthbench-rubric-judge.v1" if task.dataset_version_id.startswith("medical-healthbench") else "medqa-choice-grader.v1",
            entrypoint="workbench",
            run_id=task.task_id,
            generation_parameters={"temperature": 0.1, "max_tokens": 5120},
            judge_parameters={"temperature": 0.0, "max_tokens": 5120} if task.judge_model_id else {},
            retry_policy={"max_retries": 2, "backoff_seconds": [1.0, 2.0]},
            max_samples=task.max_samples,
            privacy={"raw_outputs_recorded": True, "credentials_recorded": False},
        )
        artifacts.write_metadata(metadata.to_dict())
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
            self._renew_execution_claim(task_id, queue_claim)
            current = self.repository.get(task_id)
            if current is not None:
                self.repository.update_progress(task_id, current.progress.model_copy(update={"stage": stage}), self.worker_id)

        def update_progress(progress: TaskProgress) -> None:
            self._renew_execution_claim(task_id, queue_claim)
            self.repository.update_progress(task_id, progress.model_copy(update={"stage": stage}), self.worker_id)

        setattr(self.adapter, "on_stage", update_stage)
        if hasattr(self.adapter, "on_sample"):
            def record_sample(sample):
                artifacts.upsert_sample(sample)
                if sample.get("error"):
                    artifacts.log(f"[sample {int(sample.get('index', 0)) + 1}] failed: {sample['error']}")
                else:
                    artifacts.log(f"[sample {int(sample.get('index', 0)) + 1}] record persisted")
            self.adapter.on_sample = record_sample
        if task.status == TaskStatus.QUEUED:
            self.repository.set_status(task_id, TaskStatus.RUNNING)

        def is_task_cancelled() -> bool:
            current_task = self.repository.get(task_id)
            return current_task is not None and current_task.status == TaskStatus.CANCELLED

        try:
            update_stage("preparing")
            result = self.adapter.run(task, update_progress, is_task_cancelled)
        except Exception as error:
            artifacts.log(f"task failed: {_safe_error(error)}")
            try:
                update_stage("failed")
            except RuntimeError:
                pass
            failed = self.repository.set_status_if_not_cancelled(
                task_id,
                TaskStatus.FAILED,
                _safe_error(error),
                self.worker_id,
            )
            return self._acknowledge_terminal_claim(failed, queue_claim)
        finally:
            for client in (getattr(self.adapter, "target_client", None), getattr(self.adapter, "judge_client", None)):
                close = getattr(client, "close", None)
                if close:
                    close()
        current = self.repository.get(task_id)
        if current is not None and current.status == TaskStatus.CANCELLED:
            return self._acknowledge_terminal_claim(current, queue_claim)
        final_stage = "partial_failed" if result.failed_count else "completed"
        final = TaskProgress(completed_count=result.total_count, total_count=result.total_count, progress_percent=100, success_count=result.success_count, failed_count=result.failed_count, retry_count=result.retry_count, stage=final_stage)
        self.repository.update_progress(task_id, final, self.worker_id)
        self.repository.save_result(task_id, total_score=result.total_score, dimension_scores=result.dimension_scores or {}, error_categories=result.error_categories or {}, completed_count=result.success_count, failed_count=result.failed_count, retry_count=result.retry_count, accuracy=result.accuracy, parse_success_rate=result.parse_success_rate, request_success_count=result.request_success_count or result.success_count, parse_failed_count=result.parse_failed_count, worker_id=self.worker_id)
        artifacts.write_summary({"task_id": task_id, "total_score": result.total_score, "accuracy": result.accuracy, "parse_success_rate": result.parse_success_rate, "completed_count": result.total_count, "failed_count": result.failed_count, "retry_count": result.retry_count, "request_success_count": result.request_success_count or result.success_count, "parse_failed_count": result.parse_failed_count})
        artifacts.log(f"[summary] completed={result.success_count} failed={result.failed_count} retries={result.retry_count} total_score={result.total_score:.4f}")
        artifacts.log("Run completed")
        completed = self.repository.set_status_if_not_cancelled(
            task_id,
            TaskStatus.PARTIAL_FAILED if result.failed_count else TaskStatus.COMPLETED,
            worker_id=self.worker_id,
        )
        return self._acknowledge_terminal_claim(completed, queue_claim)

    def _close_repository(self, repository) -> None:
        session = getattr(repository, "session", None)
        if session is not None:
            session.close()

    def _recover_and_reconcile(
        self,
        repository_factory: Callable[[], TaskRepository],
        queue: TaskQueue,
        *,
        recover_interrupted: bool,
    ) -> None:
        repository = repository_factory()
        try:
            repository.recover_expired_leases(
                "Worker lease expired before the evaluation reached a terminal state; create a retry to run it again"
            )
            if recover_interrupted:
                repository.recover_interrupted_tasks(
                    "Worker stopped before the evaluation reached a terminal state; create a retry to run it again"
                )
            list_queued = getattr(repository, "list_queued_run_ids", None)
            if list_queued is not None:
                queued_run_ids = list_queued()
                if queued_run_ids:
                    queue.reconcile(queued_run_ids)
        finally:
            self._close_repository(repository)

    def run_forever(
        self,
        queue: TaskQueue,
        repository_factory: Callable[[], TaskRepository],
        *,
        idle_seconds: float = 1.0,
    ) -> None:
        self.queue = queue
        self._recover_and_reconcile(
            repository_factory,
            queue,
            recover_interrupted=True,
        )
        while True:
            try:
                queue_claim = queue.claim_next(
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                    block_ms=max(1, int(idle_seconds * 1000)),
                )
            except Exception:
                time.sleep(idle_seconds)
                continue
            if queue_claim is None:
                try:
                    self._recover_and_reconcile(
                        repository_factory,
                        queue,
                        recover_interrupted=False,
                    )
                except Exception:
                    pass
                time.sleep(idle_seconds)
                continue
            repository = repository_factory()
            try:
                self.repository = repository
                task = repository.get(queue_claim.run_id)
                if task is None:
                    try:
                        queue.ack(queue_claim)
                    except Exception:
                        pass
                    continue
                if task.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                    self._acknowledge_terminal_claim(task, queue_claim)
                    continue
                self.run_task(queue_claim.run_id, queue_claim)
            except Exception as error:
                print(f"worker task {queue_claim.run_id} failed: {error}", flush=True)
            finally:
                self._close_repository(repository)
