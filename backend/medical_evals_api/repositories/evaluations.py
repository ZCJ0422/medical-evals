from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import (
    evaluation_definitions,
    evaluation_results,
    evaluation_runs,
    evaluation_sample_results,
    metadata,
    model_profiles,
    run_model_snapshots,
    users,
)
from ..evaluation_sources import (
    get_builtin_evaluation_definition,
    get_definition_split,
    list_builtin_evaluation_definitions,
)
from ..models.evaluations import EvaluationCreateCommand, EvaluationDefinition, EvaluationRun
from ..schemas.common import TaskProgress, TaskStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_progress(value: object) -> TaskProgress:
    if isinstance(value, TaskProgress):
        return value
    if isinstance(value, str):
        return TaskProgress.model_validate_json(value)
    if isinstance(value, dict):
        return TaskProgress.model_validate(value)
    return TaskProgress()


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class EvaluationRepository:
    def __init__(self, session: Session, artifact_root: Path | None = None):
        self.session = session
        self.artifact_root = artifact_root or settings.artifact_dir
        self._ensure_tables()
        self._seed_builtin_definitions()

    def _ensure_tables(self) -> None:
        metadata.create_all(
            self.session.bind,
            tables=[
                users,
                model_profiles,
                evaluation_definitions,
                evaluation_runs,
                run_model_snapshots,
                evaluation_results,
                evaluation_sample_results,
            ],
            checkfirst=True,
        )

    def _seed_builtin_definitions(self) -> None:
        existing = {
            row.id
            for row in self.session.execute(select(evaluation_definitions.c.id)).mappings()
        }
        inserted = False
        for definition in list_builtin_evaluation_definitions():
            if definition.id in existing:
                continue
            first_split = definition.splits[0]
            self.session.execute(
                insert(evaluation_definitions).values(
                    id=definition.id,
                    name=definition.name,
                    kind=definition.kind,
                    dataset_version=first_split.dataset_version_id,
                    requires_judge=definition.requires_judge,
                    default_config_json=definition.default_config,
                    is_enabled=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
            )
            inserted = True
        if inserted:
            self.session.commit()

    def list_definitions(self) -> list[EvaluationDefinition]:
        enabled = {
            row.id
            for row in self.session.execute(
                select(evaluation_definitions.c.id).where(
                    evaluation_definitions.c.is_enabled.is_(True)
                )
            ).mappings()
        }
        return [
            definition
            for definition in list_builtin_evaluation_definitions()
            if definition.id in enabled
        ]

    def get_definition(self, definition_id: str) -> EvaluationDefinition | None:
        row = self.session.execute(
            select(evaluation_definitions).where(
                evaluation_definitions.c.id == definition_id,
                evaluation_definitions.c.is_enabled.is_(True),
            )
        ).mappings().first()
        if row is None:
            return None
        return get_builtin_evaluation_definition(definition_id)

    def _profile_for_user(self, profile_id: str, user_id: str):
        return self.session.execute(
            select(model_profiles).where(
                model_profiles.c.id == profile_id,
                model_profiles.c.user_id == user_id,
            )
        ).mappings().first()

    def _snapshot_rows(self, run_id: str) -> dict[str, dict]:
        rows = self.session.execute(
            select(run_model_snapshots).where(run_model_snapshots.c.run_id == run_id)
        ).mappings()
        return {row["profile_role"]: dict(row) for row in rows}

    def _secret_for_profile(self, profile_id: str | None) -> str:
        if not profile_id:
            return ""
        row = self.session.execute(
            select(model_profiles.c.api_key_encrypted).where(model_profiles.c.id == profile_id)
        ).first()
        return str(row[0]) if row is not None else ""

    def _build_run(self, row) -> EvaluationRun:
        split = get_definition_split(row["evaluation_definition_id"], row["split"])
        if split is None:
            raise KeyError(f"Unknown split {row['split']!r} for {row['evaluation_definition_id']}")
        snapshots = self._snapshot_rows(row["id"])
        target_snapshot = snapshots.get("target")
        judge_snapshot = snapshots.get("judge")
        if target_snapshot is None:
            raise KeyError(f"Target snapshot missing for run {row['id']}")
        return EvaluationRun(
            run_id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            evaluation_definition_id=row["evaluation_definition_id"],
            target_model_profile_id=row["target_model_profile_id"],
            judge_model_profile_id=row["judge_model_profile_id"],
            target_model_id=target_snapshot["model_name"],
            judge_model_id=judge_snapshot["model_name"] if judge_snapshot else "",
            dataset_version_id=split.dataset_version_id,
            rubric_id=split.rubric_id,
            status=TaskStatus(row["status"]),
            progress=_coerce_progress(row["progress_json"]),
            split=row["split"],
            max_samples=row["max_samples"],
            config=dict(row["config_json"] or {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error=row["error"],
            retry_of_run_id=row["retry_of_run_id"],
            target_base_url=target_snapshot["base_url"],
            target_api_key_enc=self._secret_for_profile(row["target_model_profile_id"]),
            judge_base_url=judge_snapshot["base_url"] if judge_snapshot else "",
            judge_api_key_enc=self._secret_for_profile(row["judge_model_profile_id"]),
            lease_owner=row["lease_owner"] or "",
            lease_expires_at=row["lease_expires_at"],
        )

    def create(self, user_id: str, command: EvaluationCreateCommand) -> EvaluationRun:
        definition = self.get_definition(command.evaluation_definition_id)
        if definition is None:
            raise KeyError("evaluation_definition")
        split = get_definition_split(definition.id, command.split)
        if split is None:
            raise KeyError("split")
        target_profile = self._profile_for_user(command.target_model_profile_id, user_id)
        if target_profile is None:
            raise KeyError("target_model")
        judge_profile = None
        judge_profile_id = command.judge_model_profile_id or None
        if definition.requires_judge and judge_profile_id is None:
            raise ValueError("Judge model profile is required")
        if judge_profile_id is not None:
            judge_profile = self._profile_for_user(judge_profile_id, user_id)
            if judge_profile is None:
                raise KeyError("judge_model")
            if judge_profile["id"] == target_profile["id"]:
                raise ValueError("Target and Judge model profiles must differ")
        now = _utcnow()
        run_id = str(uuid4())
        name = command.name.strip() or f"{definition.name}-{target_profile['model_name']}-{now.strftime('%Y%m%d-%H%M%S')}"
        merged_config = dict(definition.default_config)
        merged_config.update(command.config)
        progress = TaskProgress().model_dump(mode="json")
        self.session.execute(
            insert(evaluation_runs).values(
                id=run_id,
                user_id=user_id,
                name=name,
                evaluation_definition_id=definition.id,
                target_model_profile_id=target_profile["id"],
                judge_model_profile_id=judge_profile["id"] if judge_profile else None,
                retry_of_run_id=command.retry_of_run_id,
                status=TaskStatus.QUEUED.value,
                split=split.id,
                max_samples=command.sample_limit,
                config_json=merged_config,
                progress_json=progress,
                error=None,
                lease_owner=None,
                lease_expires_at=None,
                queued_at=now,
                started_at=None,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.execute(
            insert(run_model_snapshots).values(
                id=str(uuid4()),
                run_id=run_id,
                profile_role="target",
                source_model_profile_id=target_profile["id"],
                display_name=target_profile["name"],
                base_url=target_profile["base_url"],
                model_name=target_profile["model_name"],
                api_key_encrypted="",
                created_at=now,
            )
        )
        if judge_profile is not None:
            self.session.execute(
                insert(run_model_snapshots).values(
                    id=str(uuid4()),
                    run_id=run_id,
                    profile_role="judge",
                    source_model_profile_id=judge_profile["id"],
                    display_name=judge_profile["name"],
                    base_url=judge_profile["base_url"],
                    model_name=judge_profile["model_name"],
                    api_key_encrypted="",
                    created_at=now,
                )
            )
        self.session.commit()
        created = self.get_owned(run_id, user_id)
        assert created is not None
        return created

    def get(self, run_id: str) -> EvaluationRun | None:
        row = self.session.execute(
            select(evaluation_runs).where(evaluation_runs.c.id == run_id)
        ).mappings().first()
        return self._build_run(row) if row is not None else None

    def get_owned(self, run_id: str, user_id: str) -> EvaluationRun | None:
        row = self.session.execute(
            select(evaluation_runs).where(
                evaluation_runs.c.id == run_id,
                evaluation_runs.c.user_id == user_id,
            )
        ).mappings().first()
        return self._build_run(row) if row is not None else None

    def _apply_list_filters(self, stmt, filters: dict[str, Any] | None):
        if not filters:
            return stmt
        status_values = filters.get("status_values")
        if status_values:
            stmt = stmt.where(evaluation_runs.c.status.in_(tuple(status_values)))
        created_after = _normalize_datetime(filters.get("created_after"))
        if created_after is not None:
            stmt = stmt.where(evaluation_runs.c.created_at >= created_after)
        created_before = _normalize_datetime(filters.get("created_before"))
        if created_before is not None:
            stmt = stmt.where(evaluation_runs.c.created_at <= created_before)
        limit = filters.get("limit")
        if limit is not None:
            stmt = stmt.limit(limit)
        offset = filters.get("offset")
        if offset:
            stmt = stmt.offset(offset)
        return stmt

    def list(self, filters: dict[str, Any] | None = None) -> list[EvaluationRun]:
        stmt = select(evaluation_runs).order_by(
            evaluation_runs.c.created_at.desc(),
            evaluation_runs.c.id.desc(),
        )
        stmt = self._apply_list_filters(stmt, filters)
        rows = self.session.execute(stmt).mappings()
        return [self._build_run(row) for row in rows]

    def list_owned(self, user_id: str, filters: dict[str, Any] | None = None) -> list[EvaluationRun]:
        stmt = select(evaluation_runs).where(
            evaluation_runs.c.user_id == user_id
        ).order_by(
            evaluation_runs.c.created_at.desc(),
            evaluation_runs.c.id.desc(),
        )
        stmt = self._apply_list_filters(stmt, filters)
        rows = self.session.execute(stmt).mappings()
        return [self._build_run(row) for row in rows]

    def list_queued_run_ids(self, limit: int | None = None) -> list[str]:
        stmt = (
            select(evaluation_runs.c.id)
            .where(evaluation_runs.c.status == TaskStatus.QUEUED.value)
            .order_by(evaluation_runs.c.created_at.asc(), evaluation_runs.c.id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [str(row[0]) for row in self.session.execute(stmt).all()]

    def claim(
        self,
        run_id: str,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> EvaluationRun | None:
        if not worker_id:
            raise ValueError("worker_id is required to claim a run")
        now = _utcnow()
        updated = self.session.execute(
            update(evaluation_runs)
            .where(
                evaluation_runs.c.id == run_id,
                evaluation_runs.c.status == TaskStatus.QUEUED.value,
            )
            .values(
                status=TaskStatus.RUNNING.value,
                started_at=now,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        self.session.commit()
        if not updated.rowcount:
            return None
        return self.get(run_id)

    def claim_next(self, worker_id: str = "", lease_seconds: int = 300) -> EvaluationRun | None:
        now = _utcnow()
        lease_owner = worker_id or None
        lease_expires_at = now + timedelta(seconds=lease_seconds) if lease_owner else None
        row = self.session.execute(
            select(evaluation_runs)
            .where(evaluation_runs.c.status == TaskStatus.QUEUED.value)
            .order_by(evaluation_runs.c.created_at.asc(), evaluation_runs.c.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        ).mappings().first()
        if row is None:
            return None
        updated = self.session.execute(
            update(evaluation_runs)
            .where(
                evaluation_runs.c.id == row["id"],
                evaluation_runs.c.status == TaskStatus.QUEUED.value,
            )
            .values(
                status=TaskStatus.RUNNING.value,
                started_at=row["started_at"] or now,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
        )
        self.session.commit()
        if not updated.rowcount:
            return None
        return self.get(row["id"])

    def renew_lease(self, task_id: str, worker_id: str, lease_seconds: int = 300) -> bool:
        if not worker_id:
            return False
        now = _utcnow()
        updated = self.session.execute(
            update(evaluation_runs)
            .where(
                evaluation_runs.c.id == task_id,
                evaluation_runs.c.status == TaskStatus.RUNNING.value,
                evaluation_runs.c.lease_owner == worker_id,
                evaluation_runs.c.lease_expires_at > now,
            )
            .values(
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        self.session.commit()
        return bool(updated.rowcount)

    def recover_expired_leases(self, error: str) -> list[str]:
        del error
        now = _utcnow()
        recovered_rows = self.session.execute(
            update(evaluation_runs)
            .where(
                evaluation_runs.c.status == TaskStatus.RUNNING.value,
                evaluation_runs.c.lease_owner.is_not(None),
                evaluation_runs.c.lease_expires_at.is_not(None),
                evaluation_runs.c.lease_expires_at <= now,
            )
            .values(
                status=TaskStatus.QUEUED.value,
                error=None,
                lease_owner=None,
                lease_expires_at=None,
                queued_at=now,
                finished_at=None,
                updated_at=now,
            )
            .returning(evaluation_runs.c.id)
        )
        recovered_run_ids = sorted(str(row[0]) for row in recovered_rows.all())
        self.session.commit()
        return recovered_run_ids

    def recover_interrupted_tasks(self, error: str) -> int:
        updated = self.session.execute(
            update(evaluation_runs)
            .where(
                evaluation_runs.c.status == TaskStatus.RUNNING.value,
                (evaluation_runs.c.lease_owner.is_(None))
                | (evaluation_runs.c.lease_owner == ""),
            )
            .values(
                status=TaskStatus.FAILED.value,
                error=error,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        self.session.commit()
        return int(updated.rowcount or 0)

    def update_progress(self, task_id: str, progress: TaskProgress, worker_id: str = "") -> EvaluationRun:
        now = _utcnow()
        stmt = update(evaluation_runs).where(evaluation_runs.c.id == task_id)
        if worker_id:
            stmt = stmt.where(
                evaluation_runs.c.status == TaskStatus.RUNNING.value,
                evaluation_runs.c.lease_owner == worker_id,
                evaluation_runs.c.lease_expires_at > now,
            )
        updated = self.session.execute(
            stmt.values(progress_json=progress.model_dump(mode="json"), updated_at=now)
        )
        self.session.commit()
        if worker_id and not updated.rowcount:
            if self.session.execute(
                select(evaluation_runs.c.id).where(evaluation_runs.c.id == task_id)
            ).first() is None:
                raise KeyError(task_id)
            raise RuntimeError("Worker lease lost while updating task progress")
        run = self.get(task_id)
        if run is None:
            raise KeyError(task_id)
        return run

    def set_status(self, task_id: str, status: TaskStatus, error: str | None = None) -> EvaluationRun:
        now = _utcnow()
        values = {"status": status.value, "error": error, "updated_at": now}
        if status == TaskStatus.RUNNING:
            values["started_at"] = now
            values["finished_at"] = None
        else:
            values["lease_owner"] = None
            values["lease_expires_at"] = None
        if status in {
            TaskStatus.COMPLETED,
            TaskStatus.PARTIAL_FAILED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            values["finished_at"] = now
        self.session.execute(
            update(evaluation_runs).where(evaluation_runs.c.id == task_id).values(**values)
        )
        self.session.commit()
        run = self.get(task_id)
        if run is None:
            raise KeyError(task_id)
        return run

    def set_status_if_not_cancelled(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
        worker_id: str = "",
    ) -> EvaluationRun:
        now = _utcnow()
        values = {
            "status": status.value,
            "error": error,
            "updated_at": now,
            "lease_owner": None,
            "lease_expires_at": None,
        }
        if status in {
            TaskStatus.COMPLETED,
            TaskStatus.PARTIAL_FAILED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            values["finished_at"] = now
        stmt = update(evaluation_runs).where(
            evaluation_runs.c.id == task_id,
            evaluation_runs.c.status != TaskStatus.CANCELLED.value,
        )
        if worker_id:
            stmt = stmt.where(
                evaluation_runs.c.status == TaskStatus.RUNNING.value,
                evaluation_runs.c.lease_owner == worker_id,
                evaluation_runs.c.lease_expires_at > now,
            )
        updated = self.session.execute(stmt.values(**values))
        self.session.commit()
        if not updated.rowcount:
            run = self.get(task_id)
            if run is None:
                raise KeyError(task_id)
            if worker_id and run.status != TaskStatus.CANCELLED:
                raise RuntimeError("Worker lease lost while updating task status")
            return run
        run = self.get(task_id)
        if run is None:
            raise KeyError(task_id)
        return run

    def cancel_if_active(self, task_id: str) -> tuple[EvaluationRun | None, bool]:
        now = _utcnow()
        updated = self.session.execute(
            update(evaluation_runs)
            .where(
                evaluation_runs.c.id == task_id,
                evaluation_runs.c.status.in_(
                    (TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)
                ),
            )
            .values(
                status=TaskStatus.CANCELLED.value,
                error=None,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        return self.get(task_id), bool(updated.rowcount)

    def save_result(
        self,
        task_id: str,
        *,
        total_score: float,
        dimension_scores: dict[str, float],
        error_categories: dict[str, int],
        completed_count: int,
        failed_count: int,
        retry_count: int,
        accuracy: float | None = None,
        parse_success_rate: float | None = None,
        request_success_count: int | None = None,
        parse_failed_count: int = 0,
        worker_id: str = "",
    ) -> None:
        result_id = str(uuid4())
        now = _utcnow()
        run_stmt = select(evaluation_runs.c.id).where(evaluation_runs.c.id == task_id)
        if worker_id:
            run_stmt = run_stmt.where(
                evaluation_runs.c.status == TaskStatus.RUNNING.value,
                evaluation_runs.c.lease_owner == worker_id,
                evaluation_runs.c.lease_expires_at > now,
            )
        run_row = self.session.execute(run_stmt.with_for_update()).first()
        if run_row is None:
            exists = self.session.execute(
                select(evaluation_runs.c.id).where(evaluation_runs.c.id == task_id)
            ).first()
            if exists is None:
                raise KeyError(task_id)
            if worker_id:
                raise RuntimeError("Worker lease lost while saving task result")
        existing = self.session.execute(
            select(evaluation_results.c.id).where(evaluation_results.c.run_id == task_id)
        ).first()
        payload = {
            "run_id": task_id,
            "result_version": "workbench.v1",
            "summary_json": {
                "total_score": total_score,
                "dimension_scores": dimension_scores,
                "error_categories": error_categories,
                "completed_count": completed_count,
                "failed_count": failed_count,
                "retry_count": retry_count,
                "accuracy": accuracy if accuracy is not None else total_score,
                "parse_success_rate": parse_success_rate,
                "request_success_count": request_success_count if request_success_count is not None else completed_count,
                "parse_failed_count": parse_failed_count,
            },
            "artifact_index_json": {},
            "updated_at": now,
        }
        if existing is None:
            payload["id"] = result_id
            payload["created_at"] = now
            self.session.execute(insert(evaluation_results).values(**payload))
            persisted_result_id = result_id
        else:
            self.session.execute(
                update(evaluation_results)
                .where(evaluation_results.c.run_id == task_id)
                .values(**payload)
            )
            persisted_result_id = str(existing[0])
        self.session.execute(
            update(evaluation_sample_results)
            .where(evaluation_sample_results.c.run_id == task_id)
            .values(
                evaluation_result_id=persisted_result_id,
                updated_at=now,
            )
        )
        self.session.commit()

    def get_result(self, task_id: str) -> dict | None:
        row = self.session.execute(
            select(evaluation_results).where(evaluation_results.c.run_id == task_id)
        ).mappings().first()
        if row is None:
            return None
        summary = dict(row["summary_json"] or {})
        return {
            "task_id": task_id,
            "total_score": summary.get("total_score", 0.0),
            "accuracy": summary.get("accuracy", summary.get("total_score", 0.0)),
            "parse_success_rate": summary.get("parse_success_rate"),
            "request_success_count": summary.get("request_success_count", summary.get("completed_count", 0)),
            "parse_failed_count": summary.get("parse_failed_count", 0),
            "dimension_scores": dict(summary.get("dimension_scores", {})),
            "error_categories": dict(summary.get("error_categories", {})),
            "completed_count": summary.get("completed_count", 0),
            "failed_count": summary.get("failed_count", 0),
            "retry_count": summary.get("retry_count", 0),
        }

    def upsert_sample_result(self, task_id: str, sample: dict[str, Any]) -> None:
        run = self.get(task_id)
        if run is None:
            raise KeyError(task_id)
        index = int(sample.get("index", 0))
        now = _utcnow()
        existing_result = self.session.execute(
            select(evaluation_results.c.id).where(evaluation_results.c.run_id == task_id)
        ).first()
        judge_payload = sample.get("judge")
        if judge_payload is None:
            judge_payload = sample.get("rubric_judgments")
        values = {
            "run_id": task_id,
            "evaluation_result_id": str(existing_result[0]) if existing_result is not None else None,
            "sample_index": index,
            "sample_id": str(sample.get("sample_id", "")) or None,
            "status": "failed" if sample.get("error") else "completed",
            "score": sample.get("score"),
            "judge_json": judge_payload,
            "artifact_refs_json": dict(sample),
            "output_artifact_path": f"{task_id}/samples.jsonl",
            "updated_at": now,
        }
        updated = self.session.execute(
            update(evaluation_sample_results)
            .where(
                evaluation_sample_results.c.run_id == task_id,
                evaluation_sample_results.c.sample_index == index,
            )
            .values(**values)
        )
        if updated.rowcount:
            self.session.commit()
            return
        try:
            self.session.execute(
                insert(evaluation_sample_results).values(
                    id=str(uuid4()),
                    created_at=now,
                    **values,
                )
            )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            self.session.execute(
                update(evaluation_sample_results)
                .where(
                    evaluation_sample_results.c.run_id == task_id,
                    evaluation_sample_results.c.sample_index == index,
                )
                .values(**values)
            )
            self.session.commit()

    def get_samples(self, task_id: str, offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
        run = self.get(task_id)
        if run is None:
            raise KeyError(task_id)
        total = int(
            self.session.execute(
                select(func.count())
                .select_from(evaluation_sample_results)
                .where(evaluation_sample_results.c.run_id == task_id)
            ).scalar_one()
        )
        if total == 0:
            return [], 0
        rows = self.session.execute(
            select(
                evaluation_sample_results.c.artifact_refs_json,
                evaluation_sample_results.c.sample_index,
            )
            .where(evaluation_sample_results.c.run_id == task_id)
            .order_by(evaluation_sample_results.c.sample_index.asc())
            .offset(offset)
            .limit(limit)
        ).mappings()
        records: list[dict] = []
        for row in rows:
            payload = row["artifact_refs_json"]
            if isinstance(payload, dict):
                records.append(dict(payload))
        return records, total

    def delete_if_not_running(self, task_id: str) -> str:
        row = self.session.execute(
            select(evaluation_runs.c.id, evaluation_runs.c.status)
            .where(evaluation_runs.c.id == task_id)
            .with_for_update()
        ).mappings().first()
        if row is None:
            self.session.rollback()
            return "not_found"
        if row["status"] == TaskStatus.RUNNING.value:
            self.session.rollback()
            return "conflict"
        self.session.execute(
            delete(run_model_snapshots).where(run_model_snapshots.c.run_id == task_id)
        )
        self.session.execute(
            delete(evaluation_results).where(evaluation_results.c.run_id == task_id)
        )
        self.session.execute(
            delete(evaluation_sample_results).where(evaluation_sample_results.c.run_id == task_id)
        )
        result = self.session.execute(
            delete(evaluation_runs).where(
                evaluation_runs.c.id == task_id,
                evaluation_runs.c.status != TaskStatus.RUNNING.value,
            )
        )
        if not result.rowcount:
            self.session.rollback()
            return "conflict"
        self.session.commit()
        return "deleted"

    def delete(self, task_id: str) -> bool:
        return self.delete_if_not_running(task_id) == "deleted"
