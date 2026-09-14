"""Seed only the disposable Playwright database through the current v1 model."""
from sqlalchemy.orm import Session

from medical_evals_api.config import settings
from medical_evals_api.database import get_engine, upgrade_database
from medical_evals_api.evaluator_adapter import DryRunEvaluationAdapter
from medical_evals_api.models.evaluations import EvaluationCreateCommand
from medical_evals_api.repositories.evaluations import EvaluationRepository
from medical_evals_api.repositories.users import UserRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.schemas.model_profiles import ModelProfileCreate
from medical_evals_api.services.model_profiles import ModelProfileService
from medical_evals_api.worker import Worker

upgrade_database(settings)
with Session(get_engine(settings)) as session:
    admin = UserRepository(session).ensure_default_admin()
    profile = ModelProfileService(session).create(admin.id, ModelProfileCreate(
        name="E2E target", base_url="https://example.test/v1", model_name="fixture-model", api_key="e2e-placeholder",
    ))
    repo = EvaluationRepository(session, settings.artifact_dir)
    for state in ("completed", "running"):
        run = repo.create(admin.id, EvaluationCreateCommand(
            name=f"E2E {state} result fixture", evaluation_definition_id="medqa",
            target_model_profile_id=profile.id, judge_model_profile_id=None,
            split="dev", sample_limit=1, config={},
        ))
        if state == "completed":
            Worker(repo, adapter=DryRunEvaluationAdapter()).run_task(run.run_id)
        else:
            repo.set_status(run.run_id, TaskStatus.RUNNING)
