from pydantic import BaseModel, Field


class EvaluationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_model_id: str
    judge_model_id: str
    dataset_version_id: str
    rubric_id: str


class PreflightResponse(BaseModel):
    ready: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_tokens: int | None = None
    estimated_cost: float | None = None
