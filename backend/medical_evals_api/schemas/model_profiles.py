from datetime import datetime

from pydantic import BaseModel, Field


class ModelProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=1, max_length=2048)
    model_name: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=1, max_length=4096)


class ModelProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    model_name: str | None = Field(default=None, min_length=1, max_length=255)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)


class ModelProfilePublic(BaseModel):
    id: str
    name: str
    base_url: str
    model_name: str
    has_api_key: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ModelConnectionTestResult(BaseModel):
    ok: bool
