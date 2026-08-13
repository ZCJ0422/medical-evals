import json
import uuid
from dataclasses import replace

from ..db import connect
from ..models import EvaluationTask, utc_now
from ..schemas.common import TaskProgress, TaskStatus


class TaskRepository:
    def __init__(self, database_path):
        self.database_path = database_path
        with connect(database_path):
            pass

    def create(self, *, name: str, target_model_id: str, judge_model_id: str, dataset_version_id: str, rubric_id: str) -> EvaluationTask:
        now = utc_now()
        task = EvaluationTask(uuid.uuid4().hex, name, target_model_id, judge_model_id, dataset_version_id, rubric_id, TaskStatus.QUEUED, TaskProgress(), now, now)
        with connect(self.database_path) as db:
            db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (task.task_id, task.name, task.target_model_id, task.judge_model_id, task.dataset_version_id, task.rubric_id, task.status.value, task.progress.model_dump_json(), task.created_at, task.updated_at, task.error))
        return task

    def get(self, task_id: str) -> EvaluationTask | None:
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return EvaluationTask(row["task_id"], row["name"], row["target_model_id"], row["judge_model_id"], row["dataset_version_id"], row["rubric_id"], TaskStatus(row["status"]), TaskProgress.model_validate_json(row["progress_json"]), row["created_at"], row["updated_at"], row["error"])

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
