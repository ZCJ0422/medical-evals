"""Versioned model identity and invocation metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ModelSpec:
    """Describe the model and endpoint used for an evaluation run."""

    model_id: str
    provider: str
    version: Optional[str] = None
    endpoint: Optional[str] = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.provider:
            raise ValueError("provider is required")
        self.parameters = dict(self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "version": self.version,
            "endpoint": self.endpoint,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelSpec":
        return cls(
            model_id=data["model_id"],
            provider=data["provider"],
            version=data.get("version"),
            endpoint=data.get("endpoint"),
            parameters=data.get("parameters", {}),
        )
