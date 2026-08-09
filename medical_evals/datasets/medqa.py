"""MedQA JSONL loading and validation."""

import json
from pathlib import Path
from typing import Union


OPTION_KEYS = ("A", "B", "C", "D")


def _validate_sample(sample: object, line_number: int) -> dict:
    if not isinstance(sample, dict):
        raise ValueError(f"Sample on line {line_number} must be a JSON object")

    if "question" not in sample:
        raise ValueError(f"Sample on line {line_number} must contain question")
    question = sample["question"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"Sample on line {line_number} has invalid question")

    if "options" not in sample:
        raise ValueError(f"Sample on line {line_number} must contain options")
    options = sample["options"]
    if not isinstance(options, dict) or set(options) != set(OPTION_KEYS):
        raise ValueError(f"Sample on line {line_number} must have options A, B, C, D")
    if any(not isinstance(options[key], str) for key in OPTION_KEYS):
        raise ValueError(f"Sample on line {line_number} options must be strings")

    if "answer" not in sample:
        raise ValueError(f"Sample on line {line_number} must contain answer")
    answer = sample["answer"]
    if not isinstance(answer, str) or answer.strip().upper() not in OPTION_KEYS:
        raise ValueError(f"Sample on line {line_number} has invalid answer")

    normalized = dict(sample)
    normalized["question"] = question
    normalized["options"] = {key: options[key] for key in OPTION_KEYS}
    normalized["answer"] = answer.strip().upper()
    return normalized


def load_medqa_samples(path: Union[str, Path]) -> list[dict]:
    """Load and validate MedQA samples from a UTF-8 JSONL file."""
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
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc
            samples.append(_validate_sample(sample, line_number))
    return samples
