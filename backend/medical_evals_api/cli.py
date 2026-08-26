import argparse
import uuid

import uvicorn
from sqlalchemy.orm import sessionmaker

from .config import settings, validate_runtime_security
from .database import get_engine, get_redis, upgrade_database
from .redis_queue import RedisTaskQueue
from .repositories.evaluations import EvaluationRepository
from .worker import Worker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["api", "worker", "init-db"])
    args = parser.parse_args()
    validate_runtime_security()
    if args.command == "init-db":
        upgrade_database(settings)
        engine = get_engine(settings)
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)()
        try:
            EvaluationRepository(session, settings.artifact_dir)
        finally:
            session.close()
        return
    engine = get_engine(settings)
    if args.command == "worker":
        worker_id = uuid.uuid4().hex
        session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        queue = RedisTaskQueue(get_redis(settings))

        def repository_factory() -> EvaluationRepository:
            return EvaluationRepository(session_factory(), settings.artifact_dir)

        Worker(
            repository_factory(),
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
        ).run_forever(queue, repository_factory)

    uvicorn.run("medical_evals_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
