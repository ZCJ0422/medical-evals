from datetime import datetime

from pydantic import BaseModel, Field


class MonitoringMetricsResponse(BaseModel):
    generated_at: datetime
    queue_depth: int | None = None
    queue_pending: int | None = None
    queue_error: str | None = None
    status_counts: dict[str, int] = Field(default_factory=dict)
    expired_leases: int = 0
    failure_categories: dict[str, int] = Field(default_factory=dict)
    request_success_count: int = 0
    parse_failed_count: int = 0
    parse_success_rate: float | None = None
    artifact_bytes: int = 0
    artifact_file_count: int = 0
