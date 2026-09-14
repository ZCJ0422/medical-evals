from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..schemas.common import DatasetVersionSummary
from ..schemas.evaluations import EvaluationDefinitionConfigUpdate, EvaluationDefinitionResponse, EvaluationDefinitionSplitResponse

router = APIRouter(prefix="/api", tags=["catalog"])
v1_router = APIRouter(prefix="/api/v1", tags=["catalog"])

def list_dataset_versions(session: Session) -> list[DatasetVersionSummary]:
    values: list[DatasetVersionSummary] = []
    for definition in EvaluationRepository(session).list_definitions():
        for split in definition.splits:
            values.append(
                DatasetVersionSummary(
                    dataset_version_id=split.dataset_version_id,
                    dataset_id=definition.kind,
                    rubric_id=split.rubric_id,
                    name=definition.name,
                    version=f"{split.id}.{split.version}",
                    sample_count=split.sample_count,
                )
            )
    return values


@router.get("/datasets", response_model=list[DatasetVersionSummary])
def list_datasets(
    _: AdminIdentity = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[DatasetVersionSummary]:
    return list_dataset_versions(session)


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
                    source_path=split.source_path,
                    source_sha256=split.source_sha256,
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
                source_path=split.source_path,
                source_sha256=split.source_sha256,
            )
            for split in definition.splits
        ],
        default_split=definition.default_config.get("default_split"),
        default_sample_limit=definition.default_config.get("default_sample_limit"),
        judge_model_id=definition.default_config.get("judge_model_profile_id"),
    )
