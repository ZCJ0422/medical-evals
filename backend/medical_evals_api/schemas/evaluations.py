from pydantic import BaseModel, Field


class EvaluationCreate(BaseModel):
    name: str = Field(default="", max_length=120)
    target_model_id: str
    judge_model_id: str = ""
    dataset_version_id: str
    rubric_id: str
    target_base_url: str = ""
    target_api_key: str = ""
    target_api_key_env: str = Field(default="", max_length=128)
    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_api_key_env: str = Field(default="", max_length=128)
    max_samples: int | None = Field(default=None, ge=1, le=10000)


class PreflightResponse(BaseModel):
    ready: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_tokens: int | None = None
    estimated_cost: float | None = None
