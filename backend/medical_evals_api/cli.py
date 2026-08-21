import argparse

import uvicorn
import time

from .config import settings, validate_runtime_security
from .db import connect
from .repositories.tasks import TaskRepository
from .queue import LocalTaskQueue
from .worker import Worker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["api", "worker", "init-db"])
    args = parser.parse_args()
    validate_runtime_security()
    if args.command == "init-db":
        with connect(settings.database_path):
            pass
        return
    if args.command == "worker":
        repo = TaskRepository(settings.database_path, settings.artifact_dir)
        queue = LocalTaskQueue(repo)
        repo.recover_interrupted_tasks(
            "Worker stopped before the evaluation reached a terminal state; create a retry to run it again"
        )
        while True:
            task_id = queue.claim_next()
            if task_id:
                try: Worker(repo).run_task(task_id)
                except Exception as error: print(f"worker task {task_id} failed: {error}", flush=True)
            else:
                time.sleep(1)

    uvicorn.run("medical_evals_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
