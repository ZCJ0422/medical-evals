"""Run metadata models and JSON serialization for medical evaluations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from medical_evals.models import ModelSpec


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvalRunMetadata:
    """Metadata needed to reproduce and audit one medical evaluation run."""

    eval_id: str
    dataset_version: str
    model_spec: ModelSpec
    prompt_version: str
    grader_version: str
    timestamp: str = field(default_factory=_utc_timestamp)
    run_id: Optional[str] = None

    @classmethod
    def from_run_spec(
        cls,
        run_spec: Any,
        *,
        dataset_version: str,
        model_spec: ModelSpec,
        prompt_version: str,
        grader_version: str,
    ) -> "EvalRunMetadata":
        return cls(
            eval_id=run_spec.eval_name,
            dataset_version=dataset_version,
            model_spec=model_spec,
            prompt_version=prompt_version,
            grader_version=grader_version,
            timestamp=run_spec.created_at or _utc_timestamp(),
            run_id=run_spec.run_id,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "eval_id": self.eval_id,
            "dataset_version": self.dataset_version,
            "model_spec": self.model_spec.to_dict(),
            "prompt_version": self.prompt_version,
            "grader_version": self.grader_version,
            "timestamp": self.timestamp,
        }
        if self.run_id is not None:
            payload["run_id"] = self.run_id
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def matches_sampling_event(self, event: Any) -> bool:
        """Return whether an evals sampling event belongs to this run."""
        return (
            getattr(event, "type", None) == "sampling"
            and self.run_id is not None
            and getattr(event, "run_id", None) == self.run_id
        )


def write_run_metadata(metadata: EvalRunMetadata, path: str | Path) -> Path:
    """Write one run metadata JSON document and return its path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(metadata.to_json(), encoding="utf-8")
    return output_path
