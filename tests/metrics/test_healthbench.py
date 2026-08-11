"""Tests for HealthBench weighted rubric metrics."""

from medical_evals.metrics.healthbench import (
    aggregate_samples,
    aggregate_tag_scores,
    score_rubrics,
)


def test_score_rubrics_applies_positive_max_and_negative_penalty():
    rubrics = [
        {"criterion": "safe", "points": 10, "tags": ["safety"]},
        {"criterion": "complete", "points": 6, "tags": ["completeness"]},
        {"criterion": "harmful", "points": -5, "tags": ["safety"]},
    ]
    results = [
        {"criteria_met": True},
        {"criteria_met": False},
        {"criteria_met": True},
    ]

    assert score_rubrics(rubrics, results) == {
        "achieved": 5.0,
        "positive_max": 16.0,
        "score": 5 / 16,
    }


def test_metric_handles_no_positive_points_and_clips_aggregate():
    assert score_rubrics(
        [{"criterion": "x", "points": -3, "tags": ["x"]}],
        [{"criteria_met": True}],
    )["score"] == 0.0
    assert aggregate_samples([{"score": -1.0}, {"score": 2.0}]) == 0.5


def test_aggregate_tag_scores_uses_only_rubrics_with_that_tag():
    rubrics = [
        {"criterion": "a", "points": 10, "tags": ["accuracy"]},
        {"criterion": "b", "points": 5, "tags": ["communication"]},
    ]
    results = [{"criteria_met": True}, {"criteria_met": False}]

    assert aggregate_tag_scores(rubrics, results) == {
        "accuracy": 1.0,
        "communication": 0.0,
    }
