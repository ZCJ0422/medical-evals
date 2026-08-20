"""Backward-compatible imports for the shared HealthBench metrics."""

from __future__ import annotations

from collections.abc import Sequence

from medical_evals.core.healthbench import _score_rubrics, _tag_scores


def score_rubrics(rubrics: Sequence[dict], results: Sequence[dict]) -> dict:
    return _score_rubrics(rubrics, results)


def aggregate_samples(sample_scores: Sequence[dict]) -> float:
    if not sample_scores:
        return 0.0
    return min(1.0, max(0.0, sum(float(item["score"]) for item in sample_scores) / len(sample_scores)))


def aggregate_tag_scores(rubrics: Sequence[dict], results: Sequence[dict]) -> dict[str, float]:
    return _tag_scores(rubrics, results)
