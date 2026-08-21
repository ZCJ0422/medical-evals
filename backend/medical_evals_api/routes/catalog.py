from fastapi import APIRouter, Depends

from ..auth import AdminIdentity, require_admin
from ..schemas.common import DatasetVersionSummary

router = APIRouter(prefix="/api", tags=["catalog"])

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
