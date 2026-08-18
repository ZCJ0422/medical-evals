from medical_evals_api.evaluator_adapter import healthbench_metrics


def test_healthbench_metrics_averages_weighted_sample_scores_and_tag_scores():
    metrics = healthbench_metrics(
        [
            {
                "score": 1.0,
                "tag_scores": {"safety": 1.0, "completeness": 0.5},
            },
            {
                "score": 0.25,
                "tag_scores": {"safety": 0.0},
            },
            {"error": "target request failed"},
        ]
    )

    assert metrics["score"] == 0.625
    assert metrics["tag_scores"] == {"safety": 0.5, "completeness": 0.5}
    assert metrics["completed"] == 2
    assert metrics["failed"] == 1
