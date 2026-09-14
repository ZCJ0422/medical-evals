from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import evaluation_results, evaluation_runs
from ..schemas.monitoring import MonitoringMetricsResponse


class MonitoringService:
    def __init__(self, session: Session, redis_client, artifact_root: Path, *, stream_key: str = "medical-evals:evaluations", group_name: str = "medical-evals-workers"):
        self.session = session
        self.redis = redis_client
        self.artifact_root = artifact_root
        self.stream_key = stream_key
        self.group_name = group_name

    def _queue_metrics(self) -> tuple[int | None, int | None, str | None]:
        try:
            depth = int(self.redis.xlen(self.stream_key))
            pending = self.redis.xpending(self.stream_key, self.group_name)
            if isinstance(pending, dict):
                pending_count = int(pending.get("pending", 0))
            elif isinstance(pending, (list, tuple)) and pending:
                pending_count = int(pending[0])
            else:
                pending_count = 0
            return depth, pending_count, None
        except RedisError as exc:
            return None, None, str(exc)

    def _artifact_metrics(self) -> tuple[int, int]:
        if not self.artifact_root.exists():
            return 0, 0
        total_bytes = 0
        file_count = 0
        for path in self.artifact_root.rglob("*"):
            if path.is_file():
                file_count += 1
                total_bytes += path.stat().st_size
        return total_bytes, file_count

    def snapshot(self) -> MonitoringMetricsResponse:
        queue_depth, queue_pending, queue_error = self._queue_metrics()
        status_counts = {
            row["status"]: int(row["count"])
            for row in self.session.execute(
                select(evaluation_runs.c.status, func.count().label("count")).group_by(evaluation_runs.c.status)
            ).mappings()
        }
        now = datetime.now(timezone.utc)
        lease_rows = self.session.execute(
            select(evaluation_runs.c.lease_expires_at).where(
                evaluation_runs.c.status == "running",
                evaluation_runs.c.lease_expires_at.is_not(None),
            )
        ).scalars()
        expired_leases = 0
        for lease_expires_at in lease_rows:
            # SQLite returns timezone-aware columns as naive datetimes; treat
            # those values as UTC before comparing with the current instant.
            if lease_expires_at.tzinfo is None:
                lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
            if lease_expires_at < now:
                expired_leases += 1
        failure_categories: Counter[str] = Counter()
        request_success_count = 0
        parse_failed_count = 0
        for row in self.session.execute(select(evaluation_results.c.summary_json)).mappings():
            summary = dict(row["summary_json"] or {})
            failure_categories.update({str(k): int(v) for k, v in dict(summary.get("error_categories", {})).items()})
            request_success_count += int(summary.get("request_success_count", 0) or 0)
            parse_failed_count += int(summary.get("parse_failed_count", 0) or 0)
        parsed_count = max(request_success_count - parse_failed_count, 0)
        parse_success_rate = parsed_count / request_success_count if request_success_count else None
        artifact_bytes, artifact_file_count = self._artifact_metrics()
        return MonitoringMetricsResponse(
            generated_at=now,
            queue_depth=queue_depth,
            queue_pending=queue_pending,
            queue_error=queue_error,
            status_counts=status_counts,
            expired_leases=expired_leases,
            failure_categories=dict(failure_categories),
            request_success_count=request_success_count,
            parse_failed_count=parse_failed_count,
            parse_success_rate=parse_success_rate,
            artifact_bytes=artifact_bytes,
            artifact_file_count=artifact_file_count,
        )
