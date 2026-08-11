"""HealthBench JSONL loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union


def _validate_sample(sample: object, line_number: int) -> dict:
    prefix = f"Sample on line {line_number}"
    if not isinstance(sample, dict):
        raise ValueError(f"{prefix} must be a JSON object")

    prompt_id = sample.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError(f"{prefix} has invalid prompt_id")

    prompt = sample.get("prompt")
    if not isinstance(prompt, list) or not prompt:
        raise ValueError(f"{prefix} must contain a non-empty prompt")
    normalized_prompt = []
    for message in prompt:
        if not isinstance(message, dict):
            raise ValueError(f"{prefix} prompt messages must be objects")
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not role.strip():
            raise ValueError(f"{prefix} prompt message has invalid role")
        if not isinstance(content, str):
            raise ValueError(f"{prefix} prompt message has invalid content")
        normalized_prompt.append(dict(message))

    rubrics = sample.get("rubrics")
    if not isinstance(rubrics, list) or not rubrics:
        raise ValueError(f"{prefix} must contain non-empty rubrics")
    normalized_rubrics = []
    for rubric in rubrics:
        if not isinstance(rubric, dict):
            raise ValueError(f"{prefix} rubric must be an object")
        criterion = rubric.get("criterion")
        points = rubric.get("points")
        if not isinstance(criterion, str) or not criterion.strip():
            raise ValueError(f"{prefix} rubric has invalid criterion")
        if isinstance(points, bool) or not isinstance(points, (int, float)):
            raise ValueError(f"{prefix} rubric has invalid points")
        tags = rubric.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f"{prefix} rubric has invalid tags")
        normalized = dict(rubric)
        normalized["criterion"] = criterion
        normalized["points"] = points
        normalized["tags"] = list(tags)
        normalized_rubrics.append(normalized)

    normalized_sample = dict(sample)
    normalized_sample["prompt_id"] = prompt_id
    normalized_sample["prompt"] = normalized_prompt
    normalized_sample["rubrics"] = normalized_rubrics
    return normalized_sample


def load_healthbench_samples(path: Union[str, Path]) -> list[dict]:
    """Load and validate HealthBench samples from a UTF-8 JSONL file."""
    dataset_path = Path(path)
    try:
        handle = dataset_path.open("r", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read dataset '{dataset_path}': {exc}") from exc

    samples = []
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            samples.append(_validate_sample(sample, line_number))
    return samples
