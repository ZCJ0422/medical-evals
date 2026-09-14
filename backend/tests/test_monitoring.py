from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from medical_evals_api.database import evaluation_results, evaluation_runs, metadata
from medical_evals_api.services.monitoring import MonitoringService


class FakeRedis:
    def xlen(self, _stream_key):
        return 4

    def xpending(self, _stream_key, _group_name):
        return {"pending": 2}


def test_monitoring_snapshot_aggregates_queue_runs_results_and_artifacts(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'monitoring.sqlite3'}")
    metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.execute(
            insert(evaluation_runs),
            [
                {"id": "run-1", "user_id": "u1", "name": "queued", "evaluation_definition_id": "medqa", "target_model_profile_id": "m1", "status": "queued", "split": "dev", "config_json": {}, "progress_json": {}, "lease_expires_at": None, "queued_at": now, "created_at": now, "updated_at": now},
                {"id": "run-2", "user_id": "u1", "name": "expired", "evaluation_definition_id": "medqa", "target_model_profile_id": "m1", "status": "running", "split": "dev", "config_json": {}, "progress_json": {}, "lease_expires_at": now - timedelta(minutes=1), "queued_at": now, "created_at": now, "updated_at": now},
            ],
        )
        session.execute(
            insert(evaluation_results).values(
                id="result-1",
                run_id="run-1",
                result_version="workbench.result.v2",
                summary_json={"error_categories": {"timeout": 2, "parse": 1}, "request_success_count": 10, "parse_failed_count": 2},
                artifact_index_json={},
            )
        )
        session.commit()
        artifact = tmp_path / "artifacts" / "run-1" / "summary.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}", encoding="utf-8")

        metrics = MonitoringService(session, FakeRedis(), tmp_path / "artifacts").snapshot()

    assert metrics.queue_depth == 4
    assert metrics.queue_pending == 2
    assert metrics.status_counts == {"queued": 1, "running": 1}
    assert metrics.expired_leases == 1
    assert metrics.failure_categories == {"timeout": 2, "parse": 1}
    assert metrics.request_success_count == 10
    assert metrics.parse_failed_count == 2
    assert metrics.parse_success_rate == 0.8
    assert metrics.artifact_bytes == 2
    assert metrics.artifact_file_count == 1
