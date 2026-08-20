from medical_evals.core.healthbench import aggregate_healthbench, evaluate_healthbench_sample
from medical_evals.core.models import CompletionRequest, ModelResponse


SAMPLE = {
    "prompt_id": "hb-1",
    "prompt": [{"role": "user", "content": "What should the patient do?"}],
    "rubrics": [
        {"criterion": "Gives actionable advice", "points": 2, "tags": ["safety"]},
        {"criterion": "Uses clear language", "points": 1, "tags": ["communication"]},
    ],
}


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, request: CompletionRequest, on_event=None):
        self.requests.append(request)
        return ModelResponse(text=next(self.responses), model=request.model)


def test_healthbench_core_keeps_rubrics_out_of_target_and_aggregates_tags():
    target = FakeClient(["Seek care if symptoms worsen."])
    judge = FakeClient([
        '{"criteria_met": true, "explanation": "actionable"}',
        '{"criteria_met": false, "explanation": "unclear"}',
    ])

    result = evaluate_healthbench_sample(
        target, judge, SAMPLE, target_model="target", judge_model="judge"
    )

    assert result.score == 2 / 3
    assert result.tag_scores == {"safety": 1.0, "communication": 0.0}
    assert "Gives actionable advice" not in target.requests[0].prompt[0]["content"]
    assert aggregate_healthbench([result]).dimensions["rubric_score"] == 2 / 3


def test_healthbench_core_retries_invalid_judge_json_once_then_fails_safely():
    target = FakeClient(["answer"])
    judge = FakeClient(["not json", "still not json"])

    result = evaluate_healthbench_sample(
        target, judge, SAMPLE, target_model="target", judge_model="judge"
    )

    assert result.error is not None
    assert result.error.category == "judge_parse_error"
    assert result.error.message == "judge failed: judge_parse_error"
    assert len(judge.requests) == 2
