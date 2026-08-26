from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..schemas.common import DatasetVersionSummary
from ..schemas.evaluations import EvaluationDefinitionResponse, EvaluationDefinitionSplitResponse

router = APIRouter(prefix="/api", tags=["catalog"])
v1_router = APIRouter(prefix="/api/v1", tags=["catalog"])

DATASETS = [
    DatasetVersionSummary(dataset_version_id="medical-medqa.dev.v1", dataset_id="medical-medqa", rubric_id="medical-medqa.default", name="MedQA", version="dev.v1", sample_count=3425),
    DatasetVersionSummary(dataset_version_id="medical-healthbench.smoke.v1", dataset_id="medical-healthbench", rubric_id="healthbench-default", name="HealthBench", version="smoke.v1", sample_count=2),
    DatasetVersionSummary(dataset_version_id="medical-healthbench.oss.v1", dataset_id="medical-healthbench", rubric_id="healthbench-default", name="HealthBench", version="oss.v1", sample_count=5000),
    DatasetVersionSummary(dataset_version_id="medical-healthbench.hard.v1", dataset_id="medical-healthbench", rubric_id="healthbench-default", name="HealthBench", version="hard.v1", sample_count=1000),
    DatasetVersionSummary(dataset_version_id="medical-healthbench.consensus.v1", dataset_id="medical-healthbench", rubric_id="healthbench-default", name="HealthBench", version="consensus.v1", sample_count=3671),
]


@router.get("/datasets", response_model=list[DatasetVersionSummary])
def list_datasets(_: AdminIdentity = Depends(require_admin)) -> list[DatasetVersionSummary]:
    return DATASETS


@v1_router.get("/datasets", response_model=list[EvaluationDefinitionResponse], include_in_schema=False)
def list_datasets_v1(
    _: CurrentUser,
    session: Session = Depends(get_session),
) -> list[EvaluationDefinitionResponse]:
    repository = EvaluationRepository(session)
    return [
        EvaluationDefinitionResponse(
            id=definition.id,
            name=definition.name,
            requires_judge=definition.requires_judge,
            splits=[
                EvaluationDefinitionSplitResponse(
                    id=split.id,
                    dataset_version_id=split.dataset_version_id,
                    version=split.version,
                    sample_count=split.sample_count,
                    default_sample_limit=split.default_sample_limit,
                )
                for split in definition.splits
            ],
        )
        for definition in repository.list_definitions()
    ]
