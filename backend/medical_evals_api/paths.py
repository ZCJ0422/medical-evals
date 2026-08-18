from pathlib import Path


def project_root() -> Path:
    """Return the medical-evals repository root independent of the cwd."""
    return Path(__file__).resolve().parents[2]


def registry_data_path(*parts: str) -> Path:
    """Return a path under the repository's versioned Registry data."""
    return project_root() / "registry" / "data" / Path(*parts)


def workspace_dataset_path(*parts: str) -> Path:
    """Return a path under the workspace's shared benchmark dataset directory."""
    return project_root().parent / "dataset" / Path(*parts)
