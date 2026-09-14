from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from medical_evals_api.database import evaluation_definition_splits, evaluation_definitions, metadata
from medical_evals_api.repositories.evaluations import EvaluationRepository


def test_dataset_split_catalog_is_read_from_database_and_ids_are_scoped(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'catalog.sqlite3'}")
    metadata.create_all(engine)

    with Session(engine) as session:
        repository = EvaluationRepository(session)
        session.execute(
            insert(evaluation_definitions).values(
                id="custom-eval",
                name="Custom Evaluation",
                kind="custom",
                dataset_version="custom.v1",
                requires_judge=False,
                default_config_json={"default_split": "dev"},
                is_enabled=True,
            )
        )
        session.execute(
            insert(evaluation_definition_splits).values(
                id="dev",
                evaluation_definition_id="custom-eval",
                dataset_version_id="custom.v1",
                version="v1",
                sample_count=12,
                default_sample_limit=6,
                rubric_id="custom.default",
                source_path="registry/data/custom/validation.jsonl",
                source_sha256="a" * 64,
                is_enabled=True,
            )
        )
        session.commit()

        custom = repository.get_definition("custom-eval")

    assert custom is not None
    assert custom.name == "Custom Evaluation"
    assert custom.splits[0].dataset_version_id == "custom.v1"
    assert custom.splits[0].sample_count == 12
    assert custom.splits[0].source_sha256 == "a" * 64
