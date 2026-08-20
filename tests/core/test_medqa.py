from medical_evals.core.medqa import aggregate_medqa, evaluate_medqa_sample
from medical_evals.core.models import EvaluationEvent, ModelResponse


MEDQA_SAMPLE = {
    "id": "medqa-1",
    "question": "患者出现发热，最常用的体温测量部位是什么？",
    "options": {"A": "皮肤", "B": "眼睛", "C": "口腔", "D": "头发"},
    "answer": "C",
}


class StaticClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def complete(self, request, on_event=None):
        self.requests.append(request)
        return self.response


class RetryingFailureClient:
    def complete(self, request, on_event=None):
        del request
        if on_event is not None:
            on_event(EvaluationEvent(kind="retry", stage="request", attempt=1))
            on_event(EvaluationEvent(kind="retry", stage="request", attempt=2))
        error = RuntimeError("request timed out")
        error.is_timeout = True
        raise error


def test_medqa_uses_one_canonical_prompt_and_result_shape():
    client = StaticClient(ModelResponse(text="C", retry_count=1))

    result = evaluate_medqa_sample(client, MEDQA_SAMPLE, model="model-a")

    assert "请只输出一个选项字母" in client.requests[0].prompt
    assert result.predicted == "C"
    assert result.correct is True
    assert result.retry_count == 1


def test_medqa_parse_failure_is_not_a_request_failure():
    client = StaticClient(ModelResponse(text="无法确定"))

    result = evaluate_medqa_sample(client, MEDQA_SAMPLE, model="model-a")

    assert result.parse_failed is True
    assert result.error is None
    assert aggregate_medqa([result]).failed_count == 0


def test_medqa_request_exception_returns_normalized_failed_result():
    result = evaluate_medqa_sample(RetryingFailureClient(), MEDQA_SAMPLE, model="model-a")

    assert result.correct is False
    assert result.parse_failed is False
    assert result.retry_count == 2
    assert result.error is not None
    assert result.error.category == "timeout_error"
    assert result.error.message == "request timed out"


def test_medqa_aggregate_counts_request_and_parse_failures_as_incorrect():
    correct = evaluate_medqa_sample(
        StaticClient(ModelResponse(text="C")), MEDQA_SAMPLE, model="model-a"
    )
    parse_failed = evaluate_medqa_sample(
        StaticClient(ModelResponse(text="无法确定")), MEDQA_SAMPLE, model="model-a"
    )
    request_failed = evaluate_medqa_sample(
        RetryingFailureClient(), MEDQA_SAMPLE, model="model-a"
    )

    summary = aggregate_medqa([correct, parse_failed, request_failed])

    assert summary.total_count == 3
    assert summary.failed_count == 1
    assert summary.total_score == 1 / 3
    assert summary.request_success_count == 2
    assert summary.parse_failed_count == 1
    assert summary.parse_success_rate == 1 / 2
    assert summary.retry_count == 2
    assert summary.error_categories == {"timeout_error": 1}
