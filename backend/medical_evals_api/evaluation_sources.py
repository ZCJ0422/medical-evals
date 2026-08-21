"""Versioned Workbench dataset source resolution."""

from .paths import registry_data_path, workspace_dataset_path


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
