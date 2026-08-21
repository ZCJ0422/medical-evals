from __future__ import annotations

import builtins
import json
import uuid
from dataclasses import replace

from ..db import connect
from ..artifacts import artifact_root_for_database
from ..models import EvaluationTask, utc_now
from ..schemas.common import TaskProgress, TaskStatus


class TaskRepository:
    def __init__(self, database_path, artifact_root=None):
        self.database_path = database_path
        self.artifact_root = artifact_root or artifact_root_for_database(database_path)
        with connect(database_path):
            pass

    def create(self, *, name: str, target_model_id: str, judge_model_id: str, dataset_version_id: str, rubric_id: str, target_base_url: str = "", target_api_key_enc: str = "", judge_base_url: str = "", judge_api_key_enc: str = "", target_api_key_env: str = "", judge_api_key_env: str = "", max_samples: int | None = None) -> EvaluationTask:
        now = utc_now()
        task = EvaluationTask(
            task_id=uuid.uuid4().hex,
            name=name,
            target_model_id=target_model_id,
            judge_model_id=judge_model_id,
            dataset_version_id=dataset_version_id,
            rubric_id=rubric_id,
            status=TaskStatus.QUEUED,
            progress=TaskProgress(),
            created_at=now,
            updated_at=now,
            target_base_url=target_base_url,
            target_api_key_env=target_api_key_env,
            target_api_key_enc=target_api_key_enc,
            judge_base_url=judge_base_url,
            judge_api_key_env=judge_api_key_env,
            judge_api_key_enc=judge_api_key_enc,
            max_samples=max_samples,
        )
        with connect(self.database_path) as db:
            db.execute("INSERT INTO tasks (task_id,name,target_model_id,judge_model_id,dataset_version_id,rubric_id,status,progress_json,created_at,updated_at,error,target_base_url,target_api_key_env,judge_base_url,judge_api_key_env,max_samples,target_api_key_enc,judge_api_key_enc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (task.task_id, task.name, task.target_model_id, task.judge_model_id, task.dataset_version_id, task.rubric_id, task.status.value, task.progress.model_dump_json(), task.created_at, task.updated_at, task.error, target_base_url, target_api_key_env, judge_base_url, judge_api_key_env, max_samples, target_api_key_enc, judge_api_key_enc))
        return task

    def get(self, task_id: str) -> EvaluationTask | None:
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return EvaluationTask(row["task_id"], row["name"], row["target_model_id"], row["judge_model_id"], row["dataset_version_id"], row["rubric_id"], TaskStatus(row["status"]), TaskProgress.model_validate_json(row["progress_json"]), row["created_at"], row["updated_at"], row["error"], row["target_base_url"], row["target_api_key_env"], row["target_api_key_enc"], row["judge_base_url"], row["judge_api_key_env"], row["judge_api_key_enc"], row["max_samples"])

    def next_queued(self) -> EvaluationTask | None:
        with connect(self.database_path) as db:
            row = db.execute("SELECT task_id FROM tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1").fetchone()
        return self.get(row["task_id"]) if row else None

    def claim_next(self) -> EvaluationTask | None:
        """Atomically move one queued task to running and return it."""
        with connect(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT task_id FROM tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            updated = db.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ? AND status = ?",
                (TaskStatus.RUNNING.value, now, row["task_id"], TaskStatus.QUEUED.value),
            )
            if updated.rowcount != 1:
                return None
            claimed_id = row["task_id"]
        return self.get(claimed_id)

    def list(self) -> list[EvaluationTask]:
        with connect(self.database_path) as db:
            rows = db.execute("SELECT task_id FROM tasks ORDER BY created_at DESC").fetchall()
        return [task for row in rows if (task := self.get(row["task_id"])) is not None]

    def save_result(self, task_id: str, *, total_score: float, dimension_scores: dict[str, float], error_categories: dict[str, int], completed_count: int, failed_count: int, retry_count: int, accuracy: float | None = None, parse_success_rate: float | None = None, request_success_count: int | None = None, parse_failed_count: int = 0) -> None:
        if self.get(task_id) is None:
            raise KeyError(task_id)
        with connect(self.database_path) as db:
            db.execute("INSERT OR REPLACE INTO task_results (task_id,total_score,dimension_scores_json,error_categories_json,completed_count,failed_count,retry_count,accuracy,parse_success_rate,request_success_count,parse_failed_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (task_id, total_score, json.dumps(dimension_scores), json.dumps(error_categories), completed_count, failed_count, retry_count, accuracy, parse_success_rate, request_success_count if request_success_count is not None else completed_count, parse_failed_count))

    def get_result(self, task_id: str) -> dict | None:
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM task_results WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return {"task_id": task_id, "total_score": row["total_score"], "accuracy": row["accuracy"] if row["accuracy"] is not None else row["total_score"], "parse_success_rate": row["parse_success_rate"], "request_success_count": row["request_success_count"], "parse_failed_count": row["parse_failed_count"], "dimension_scores": json.loads(row["dimension_scores_json"]), "error_categories": json.loads(row["error_categories_json"]), "completed_count": row["completed_count"], "failed_count": row["failed_count"], "retry_count": row["retry_count"]}

    def get_samples(self, task_id: str, offset: int = 0, limit: int = 50) -> tuple[builtins.list[dict], int]:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        path = self.artifact_root / task_id / "samples.jsonl"
        if not path.exists():
            return [], 0
        records: builtins.list[dict] = []
        total = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(value, dict):
                    continue
                if total >= offset and len(records) < limit:
                    records.append(value)
                total += 1
        return records, total

    def delete(self, task_id: str) -> bool:
        with connect(self.database_path) as db:
            cursor = db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            db.execute("DELETE FROM task_results WHERE task_id = ?", (task_id,))
        return cursor.rowcount > 0

    def update_progress(self, task_id: str, progress: TaskProgress) -> EvaluationTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        updated = replace(task, progress=progress, updated_at=utc_now())
        with connect(self.database_path) as db:
            db.execute("UPDATE tasks SET progress_json = ?, updated_at = ? WHERE task_id = ?", (progress.model_dump_json(), updated.updated_at, task_id))
        return updated

    def set_status(self, task_id: str, status: TaskStatus, error: str | None = None) -> EvaluationTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        updated = replace(task, status=status, error=error, updated_at=utc_now())
        with connect(self.database_path) as db:
            db.execute("UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE task_id = ?", (status.value, error, updated.updated_at, task_id))
        return updated

    def set_status_if_not_cancelled(self, task_id: str, status: TaskStatus, error: str | None = None) -> EvaluationTask:
        """Set a terminal status without overwriting a concurrent cancellation."""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        updated_at = utc_now()
        with connect(self.database_path) as db:
            updated = db.execute(
                "UPDATE tasks SET status = ?, error = ?, updated_at = ? "
                "WHERE task_id = ? AND status != ?",
                (status.value, error, updated_at, task_id, TaskStatus.CANCELLED.value),
            )
        if updated.rowcount == 0:
            return self.get(task_id) or task
        return replace(task, status=status, error=error, updated_at=updated_at)

    def recover_interrupted_tasks(self, error: str) -> int:
        """Mark tasks left running by a stopped Worker as failed.

        A new Worker must not silently re-run a task whose checkpoint may have
        been partially written. The user can explicitly create a retry after
        inspecting the preserved artifacts.
        """
        with connect(self.database_path) as db:
            updated = db.execute(
                "UPDATE tasks SET status = ?, error = ?, updated_at = ? "
                "WHERE status = ?",
                (
                    TaskStatus.FAILED.value,
                    error,
                    utc_now(),
                    TaskStatus.RUNNING.value,
                ),
            )
        return updated.rowcount
