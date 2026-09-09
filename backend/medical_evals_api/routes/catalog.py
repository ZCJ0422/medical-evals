from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..schemas.common import DatasetVersionSummary
from ..schemas.evaluations import EvaluationDefinitionConfigUpdate, EvaluationDefinitionResponse, EvaluationDefinitionSplitResponse

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


@v1_router.get("/datasets", response_model=list[EvaluationDefinitionResponse])
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
            default_split=definition.default_config.get("default_split") or definition.splits[0].id,
            default_sample_limit=definition.default_config.get("default_sample_limit") or definition.splits[0].default_sample_limit,
            judge_model_id=definition.default_config.get("judge_model_profile_id"),
        )
        for definition in repository.list_definitions()
    ]


@v1_router.patch("/datasets/{definition_id}/config", response_model=EvaluationDefinitionResponse)
def update_dataset_config(
    definition_id: str,
    payload: EvaluationDefinitionConfigUpdate,
    _: AdminIdentity = Depends(require_admin),
    session: Session = Depends(get_session),
) -> EvaluationDefinitionResponse:
    repository = EvaluationRepository(session)
    try:
        definition = repository.update_definition_config(
            definition_id,
            default_split=payload.default_split,
            default_sample_limit=payload.default_sample_limit,
            judge_model_id=payload.judge_model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if definition is None:
        raise HTTPException(status_code=404, detail="Evaluation definition or split not found")
    return EvaluationDefinitionResponse(
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
        default_split=definition.default_config.get("default_split"),
        default_sample_limit=definition.default_config.get("default_sample_limit"),
        judge_model_id=definition.default_config.get("judge_model_profile_id"),
    )
