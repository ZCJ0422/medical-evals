from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from medical_evals_api.database import metadata
from medical_evals_api.evaluator_adapter import healthbench_samples_path
from medical_evals_api.routes.catalog import list_dataset_versions


def test_catalog_sample_counts_match_registered_dataset_versions(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'catalog.sqlite3'}")
    metadata.create_all(engine)
    with Session(engine) as session:
        counts = {item.dataset_version_id: item.sample_count for item in list_dataset_versions(session)}

    assert counts == {
        "medical-medqa.dev.v1": 3425,
        "medical-healthbench.smoke.v1": 2,
        "medical-healthbench.oss.v1": 5000,
        "medical-healthbench.hard.v1": 1000,
        "medical-healthbench.consensus.v1": 3671,
    }


def test_healthbench_version_maps_to_its_source_file():
    assert healthbench_samples_path("medical-healthbench.smoke.v1").name == "smoke.jsonl"
    assert healthbench_samples_path("medical-healthbench.oss.v1").name == "2025-05-07-06-14-12_oss_eval.jsonl"
    assert healthbench_samples_path("medical-healthbench.hard.v1").name == "hard_2025-05-08-21-00-10.jsonl"
    assert healthbench_samples_path("medical-healthbench.consensus.v1").name == "consensus_2025-05-09-20-00-46.jsonl"
