"""Weighted rubric metrics for HealthBench."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))


def score_rubrics(rubrics: Sequence[dict], results: Sequence[dict]) -> dict:
    """Score one sample's rubric judgments."""
    if len(rubrics) != len(results):
        raise ValueError("rubrics and results must have the same length")
    achieved = 0.0
    positive_max = 0.0
    for rubric, result in zip(rubrics, results):
        points = float(rubric["points"])
        if points > 0:
            positive_max += points
        if result.get("criteria_met") is True:
            achieved += points
    score = achieved / positive_max if positive_max else 0.0
    return {
        "achieved": achieved,
        "positive_max": positive_max,
        "score": score,
    }


def aggregate_samples(sample_scores: Sequence[dict]) -> float:
    """Return the clipped mean of sample scores."""
    if not sample_scores:
        return 0.0
    return _clip(sum(float(item["score"]) for item in sample_scores) / len(sample_scores))


def aggregate_tag_scores(rubrics: Sequence[dict], results: Sequence[dict]) -> dict[str, float]:
    """Calculate weighted scores independently for each rubric tag."""
    grouped: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for rubric, result in zip(rubrics, results):
        for tag in rubric.get("tags", []):
            grouped[tag].append((rubric, result))
    return {
        tag: score_rubrics([item[0] for item in items], [item[1] for item in items])["score"]
        for tag, items in grouped.items()
    }
