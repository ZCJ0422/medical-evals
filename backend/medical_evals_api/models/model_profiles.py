from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ModelProfile:
    id: str
    user_id: str
    name: str
    base_url: str
    model_name: str
    api_key_encrypted: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
