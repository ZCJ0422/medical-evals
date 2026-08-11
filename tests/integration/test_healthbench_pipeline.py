"""End-to-end HealthBench pipeline tests with a fake compatible client."""

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from evals.base import RunSpec
from evals.record import DummyRecorder
from evals.registry import Registry

from medical_evals.adapters import OpenAICompatibleCompletionFn
from medical_evals.evals import HealthBenchEval


class FakeChatCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class FakeOpenAIClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(responses))


def make_response(content, model="fake-health-model"):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def make_recorder():
    return DummyRecorder(
        RunSpec(
            completion_fns=["fake-openai"],
            eval_name="medical-healthbench.smoke.v1",
            base_eval="medical-healthbench",
            split="smoke",
            run_config={},
            created_by="integration-test",
        ),
        log=False,
    )


def test_registry_loads_healthbench_specs():
    registry = Registry([Path("registry")])
    for name in (
        "medical-healthbench.smoke.v1",
        "medical-healthbench.oss.v1",
        "medical-healthbench.hard.v1",
        "medical-healthbench.consensus.v1",
    ):
        spec = registry.get_eval(name)
        assert spec is not None
        assert spec.cls == "medical_evals.evals.healthbench:HealthBenchEval"


def test_healthbench_pipeline_generates_and_judges_smoke_samples(monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    target_client = FakeOpenAIClient(
        [make_response("Seek care if symptoms worsen.")] * 2
    )
    judge_client = FakeOpenAIClient(
        [
            make_response('{"criteria_met": true, "explanation": "covered"}', "judge-model"),
            make_response('{"criteria_met": false, "explanation": "not present"}', "judge-model"),
            make_response('{"criteria_met": true, "explanation": "covered"}', "judge-model"),
            make_response('{"criteria_met": true, "explanation": "clear"}', "judge-model"),
        ]
    )
    target = OpenAICompatibleCompletionFn(model="target-model", client=target_client, max_retries=0)
    judge = OpenAICompatibleCompletionFn(model="judge-model", client=judge_client, max_retries=0)
    registry = Registry([Path("registry")])
    evaluation = HealthBenchEval(
        completion_fns=[target],
        eval_registry_path=Path("registry"),
        registry=registry,
        name="medical-healthbench.smoke.v1",
        samples_jsonl="medical_healthbench/smoke.jsonl",
        judge_completion_fn=judge,
    )

    result = evaluation.run(make_recorder())

    assert len(target_client.chat.completions.calls) == 2
    assert len(judge_client.chat.completions.calls) == 4
    target_payload = str(target_client.chat.completions.calls[0]["messages"])
    assert "Recognizes that sudden" not in target_payload
    assert result["sample_count"] == 2
    assert result["overall_score"] > 0
    assert "safety" in result["tag_scores"]
