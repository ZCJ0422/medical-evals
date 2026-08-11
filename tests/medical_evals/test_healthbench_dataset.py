"""Tests for HealthBench JSONL loading and validation."""

import json

import pytest

from medical_evals.datasets.healthbench import load_healthbench_samples


def test_load_healthbench_samples_normalizes_tags_and_preserves_fields(tmp_path):
    path = tmp_path / "healthbench.jsonl"
    path.write_text(
        json.dumps(
            {
                "prompt_id": "p1",
                "prompt": [{"role": "user", "content": "What should I do?"}],
                "rubrics": [{"criterion": "Gives safe advice", "points": 10}],
                "ideal_completions_data": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    samples = load_healthbench_samples(path)

    assert samples[0]["prompt_id"] == "p1"
    assert samples[0]["rubrics"][0]["tags"] == []
    assert samples[0]["ideal_completions_data"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt_id": "p1", "prompt": [], "rubrics": []},
        {
            "prompt_id": "p1",
            "prompt": [{"role": "user"}],
            "rubrics": [{"criterion": "x", "points": 1}],
        },
        {
            "prompt_id": "p1",
            "prompt": [{"role": "user", "content": "x"}],
            "rubrics": [{"criterion": "x", "points": "1"}],
        },
    ],
)
def test_loader_rejects_invalid_rows(tmp_path, payload):
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        load_healthbench_samples(path)
