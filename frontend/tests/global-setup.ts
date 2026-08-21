import { execFileSync } from "node:child_process";
import path from "node:path";

export default function globalSetup() {
  const backendDir = path.resolve(__dirname, "../../backend");
  const code = [
    "from medical_evals_api.repositories.tasks import TaskRepository",
    "from medical_evals_api.worker import Worker",
    "from medical_evals_api.evaluator_adapter import DryRunEvaluationAdapter",
    "from pathlib import Path",
    "repo = TaskRepository(Path('data/medical-evals.sqlite3'))",
    "task = repo.create(name='E2E completed result fixture', target_model_id='fixture-model', judge_model_id='', dataset_version_id='medical-medqa.dev.v1', rubric_id='medical-medqa.default', max_samples=1)",
    "Worker(repo, adapter=DryRunEvaluationAdapter()).run_task(task.task_id)",
    "running = repo.create(name='E2E running result fixture', target_model_id='fixture-model', judge_model_id='', dataset_version_id='medical-medqa.dev.v1', rubric_id='medical-medqa.default', max_samples=2)",
    "repo.set_status(running.task_id, __import__('medical_evals_api.schemas.common', fromlist=['TaskStatus']).TaskStatus.RUNNING)",
  ].join("; ");
  execFileSync("uv", ["run", "python", "-c", code], { cwd: backendDir, env: { ...process.env }, stdio: "inherit" });
}
