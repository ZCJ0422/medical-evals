"""Tests for the Phase 1.1 MedQA dataset loader."""

import json

import pytest

from medical_evals.datasets.medqa import load_medqa_samples


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_load_medqa_samples_normalizes_answer_and_preserves_semantics(tmp_path):
    path = tmp_path / "samples.jsonl"
    write_jsonl(
        path,
        [
            {
                "question": "示例题目",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                "answer": "c",
            }
        ],
    )

    samples = load_medqa_samples(path)

    assert samples == [
        {
            "question": "示例题目",
            "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            "answer": "C",
        }
    ]


@pytest.mark.parametrize(
    "sample, message",
    [
        (
            {"options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "answer": "A"},
            "question",
        ),
        (
            {"question": "题目", "options": {"A": "甲"}, "answer": "A"},
            "options A, B, C, D",
        ),
        (
            {
                "question": "题目",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                "answer": "E",
            },
            "invalid answer",
        ),
    ],
)
def test_load_medqa_samples_rejects_invalid_rows(tmp_path, sample, message):
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [sample])

    with pytest.raises(ValueError, match=message):
        load_medqa_samples(path)
