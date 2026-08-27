"""Versioned Workbench evaluation definitions and dataset source resolution."""

from __future__ import annotations

from .models.evaluations import EvaluationDefinition, EvaluationDefinitionSplit
from .paths import registry_data_path, workspace_dataset_path


BUILTIN_EVALUATION_DEFINITIONS: tuple[EvaluationDefinition, ...] = (
    EvaluationDefinition(
        id="medqa",
        name="MedQA",
        kind="medical-medqa",
        requires_judge=False,
        default_config={},
        splits=(
            EvaluationDefinitionSplit(
                id="dev",
                dataset_version_id="medical-medqa.dev.v1",
                version="v1",
                sample_count=3425,
                default_sample_limit=3425,
                rubric_id="medical-medqa.default",
            ),
        ),
    ),
    EvaluationDefinition(
        id="healthbench",
        name="HealthBench",
        kind="medical-healthbench",
        requires_judge=True,
        default_config={},
        splits=(
            EvaluationDefinitionSplit(
                id="smoke",
                dataset_version_id="medical-healthbench.smoke.v1",
                version="v1",
                sample_count=2,
                default_sample_limit=2,
                rubric_id="healthbench-default",
            ),
            EvaluationDefinitionSplit(
                id="oss",
                dataset_version_id="medical-healthbench.oss.v1",
                version="v1",
                sample_count=5000,
                default_sample_limit=5000,
                rubric_id="healthbench-default",
            ),
            EvaluationDefinitionSplit(
                id="hard",
                dataset_version_id="medical-healthbench.hard.v1",
                version="v1",
                sample_count=1000,
                default_sample_limit=1000,
                rubric_id="healthbench-default",
            ),
            EvaluationDefinitionSplit(
                id="consensus",
                dataset_version_id="medical-healthbench.consensus.v1",
                version="v1",
                sample_count=3671,
                default_sample_limit=3671,
                rubric_id="healthbench-default",
            ),
        ),
    ),
)


def list_builtin_evaluation_definitions() -> tuple[EvaluationDefinition, ...]:
    return BUILTIN_EVALUATION_DEFINITIONS


def get_builtin_evaluation_definition(definition_id: str) -> EvaluationDefinition | None:
    for definition in BUILTIN_EVALUATION_DEFINITIONS:
        if definition.id == definition_id:
            return definition
    return None


def get_definition_split(
    definition_id: str,
    split_id: str | None,
) -> EvaluationDefinitionSplit | None:
    definition = get_builtin_evaluation_definition(definition_id)
    if definition is None:
        return None
    chosen_split = split_id or definition.splits[0].id
    for split in definition.splits:
        if split.id == chosen_split:
            return split
    return None


def healthbench_samples_path(dataset_version_id: str):
    """Resolve a HealthBench version to the data file it actually represents."""
    sources = {
        "medical-healthbench.smoke.v1": registry_data_path("medical_healthbench", "smoke.jsonl"),
        "medical-healthbench.oss.v1": workspace_dataset_path("HealthBench", "2025-05-07-06-14-12_oss_eval.jsonl"),
        "medical-healthbench.hard.v1": workspace_dataset_path("HealthBench", "hard_2025-05-08-21-00-10.jsonl"),
        "medical-healthbench.consensus.v1": workspace_dataset_path("HealthBench", "consensus_2025-05-09-20-00-46.jsonl"),
    }
    try:
        return sources[dataset_version_id]
    except KeyError as error:
        raise ValueError(f"Unsupported HealthBench dataset version: {dataset_version_id}") from error
