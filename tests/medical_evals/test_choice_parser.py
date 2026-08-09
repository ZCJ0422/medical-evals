"""Tests for the MedQA choice parser."""

import pytest

from medical_evals.graders.choice_parser import parse_choice


@pytest.mark.parametrize(
    "text, expected",
    [
        ("A", "A"),
        ("b", "B"),
        ("C", "C"),
        ("D", "D"),
        ("答案：C", "C"),
        ("选项 C", "C"),
        ("最终答案为：D", "D"),
        ("<think>分析</think>\nB", "B"),
        ("<think>需要比较四个选项</think>\nC", "C"),
        ("答案不确定", None),
        ("A 或 B", None),
    ],
)
def test_parse_choice(text, expected):
    assert parse_choice(text) == expected
