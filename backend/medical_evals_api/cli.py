import argparse
import uuid

import uvicorn
import time
from sqlalchemy.orm import sessionmaker

from .config import settings, validate_runtime_security
from .database import get_engine, metadata
from .repositories.evaluations import EvaluationRepository
from .queue import LocalTaskQueue, TaskQueue
from .worker import Worker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["api", "worker", "init-db"])
    args = parser.parse_args()
    validate_runtime_security()
    engine = get_engine(settings)
    if args.command == "init-db":
        metadata.create_all(engine, checkfirst=True)
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)()
        try:
            EvaluationRepository(session, settings.artifact_dir)
        finally:
            session.close()
        return
    if args.command == "worker":
        worker_id = uuid.uuid4().hex
        session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        startup_session = session_factory()
        try:
            startup_repo = EvaluationRepository(startup_session, settings.artifact_dir)
            startup_repo.recover_expired_leases(
                "Worker lease expired before the evaluation reached a terminal state; create a retry to run it again"
            )
            startup_repo.recover_interrupted_tasks(
                "Worker stopped before the evaluation reached a terminal state; create a retry to run it again"
            )
        finally:
            startup_session.close()
        while True:
            claim_session = session_factory()
            try:
                repo = EvaluationRepository(claim_session, settings.artifact_dir)
                repo.recover_expired_leases(
                    "Worker lease expired before the evaluation reached a terminal state; create a retry to run it again"
                )
                queue: TaskQueue = LocalTaskQueue(repo)
                task_id = queue.claim_next(worker_id, settings.worker_lease_seconds)
            finally:
                claim_session.close()
            if task_id:
                run_session = session_factory()
                try:
                    Worker(
                        EvaluationRepository(run_session, settings.artifact_dir),
                        worker_id=worker_id,
                        lease_seconds=settings.worker_lease_seconds,
                    ).run_task(task_id)
                except Exception as error:
                    print(f"worker task {task_id} failed: {error}", flush=True)
                finally:
                    run_session.close()
            else:
                time.sleep(1)

    uvicorn.run("medical_evals_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
