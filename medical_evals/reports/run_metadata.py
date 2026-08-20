"""Run metadata models and JSON serialization for medical evaluations."""

from __future__ import annotations

import json
import hashlib
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
    schema_version: str = "eval-run-metadata.v2"
    benchmark: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_sha256: Optional[str] = None
    dataset_sample_count: Optional[int] = None
    entrypoint: Optional[str] = None
    code_version: Optional[str] = None
    rubric_version: Optional[str] = None
    target_model_spec: Optional[ModelSpec] = None
    judge_model_spec: Optional[ModelSpec] = None
    generation_parameters: dict[str, Any] = field(default_factory=dict)
    judge_parameters: dict[str, Any] = field(default_factory=dict)
    retry_policy: dict[str, Any] = field(default_factory=dict)
    seed: Optional[int] = None
    max_samples: Optional[int] = None
    privacy: dict[str, Any] = field(default_factory=lambda: {
        "raw_outputs_recorded": False,
        "credentials_recorded": False,
    })

    @classmethod
    def from_run_spec(
        cls,
        run_spec: Any,
        *,
        dataset_version: str,
        model_spec: ModelSpec,
        prompt_version: str,
        grader_version: str,
        **metadata: Any,
    ) -> "EvalRunMetadata":
        return cls(
            eval_id=run_spec.eval_name,
            dataset_version=dataset_version,
            model_spec=model_spec,
            prompt_version=prompt_version,
            grader_version=grader_version,
            timestamp=run_spec.created_at or _utc_timestamp(),
            run_id=run_spec.run_id,
            benchmark=metadata.pop("benchmark", run_spec.base_eval),
            dataset_id=metadata.pop("dataset_id", run_spec.base_eval),
            entrypoint=metadata.pop("entrypoint", "oaieval"),
            **metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "eval_id": self.eval_id,
            "dataset_version": self.dataset_version,
            "model_spec": self.model_spec.to_dict(),
            "prompt_version": self.prompt_version,
            "grader_version": self.grader_version,
            "timestamp": self.timestamp,
        }
        if self.run_id is not None:
            payload["run_id"] = self.run_id
        optional = {
            "benchmark": self.benchmark,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "dataset_sample_count": self.dataset_sample_count,
            "entrypoint": self.entrypoint,
            "code_version": self.code_version,
            "rubric_version": self.rubric_version,
            "seed": self.seed,
            "max_samples": self.max_samples,
        }
        for key, value in optional.items():
            if value is not None:
                payload[key] = value
        if self.target_model_spec is not None:
            payload["target_model_spec"] = self.target_model_spec.to_dict()
        if self.judge_model_spec is not None:
            payload["judge_model_spec"] = self.judge_model_spec.to_dict()
        if self.generation_parameters:
            payload["generation_parameters"] = dict(self.generation_parameters)
        if self.judge_parameters:
            payload["judge_parameters"] = dict(self.judge_parameters)
        if self.retry_policy:
            payload["retry_policy"] = dict(self.retry_policy)
        payload["privacy"] = dict(self.privacy)
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


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a stable content fingerprint without storing dataset contents."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
