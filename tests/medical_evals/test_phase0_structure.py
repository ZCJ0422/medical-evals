"""Smoke tests for the medical_evals package and repository boundaries."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]


def test_medical_evals_extension_packages_are_importable():
    import medical_evals.adapters
    import medical_evals.datasets
    import medical_evals.evals
    import medical_evals.graders
    import medical_evals.human
    import medical_evals.judges
    import medical_evals.metrics
    import medical_evals.models
    import medical_evals.reports

    assert medical_evals.adapters is not None
    assert medical_evals.datasets is not None
    assert medical_evals.evals is not None
    assert medical_evals.graders is not None
    assert medical_evals.human is not None
    assert medical_evals.judges is not None
    assert medical_evals.metrics is not None
    assert medical_evals.models is not None
    assert medical_evals.reports is not None


def test_phase05_repository_directories_exist():
    expected_directories = [
        "medical_evals",
        "tests/medical_evals",
        "tests/adapters",
        "tests/metrics",
        "tests/integration",
        "registry/evals",
        "registry/datasets",
        "registry/models",
        "registry/judges",
        "experiments/configs",
        "experiments/runs",
        "experiments/snapshots",
        "docs",
    ]

    for directory in expected_directories:
        assert (PROJECT_ROOT / directory).is_dir(), directory
