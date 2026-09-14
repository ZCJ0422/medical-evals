from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..database import get_redis, get_session
from ..schemas.monitoring import MonitoringMetricsResponse
from ..services.monitoring import MonitoringService


router = APIRouter(prefix="/api/v1/ops", tags=["monitoring"])


@router.get("/metrics", response_model=MonitoringMetricsResponse)
def metrics(
    _: AdminIdentity = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MonitoringMetricsResponse:
    return MonitoringService(session, get_redis(settings), settings.artifact_dir).snapshot()
