"""Tests for HealthBench Eval orchestration."""

import json
from pathlib import Path

from evals.base import RunSpec
from evals.record import DummyRecorder

from medical_evals.evals.healthbench import HealthBenchEval


class PresetCompletionResult:
    def __init__(self, text):
        self.text = text

    def get_completions(self):
        return [self.text]


class PresetCompletionFn:
    def __init__(self, responses, model="test-model"):
        self.responses = iter(responses)
        self.prompts = []
        self.kwargs = []
        self.model = model

    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        return PresetCompletionResult(next(self.responses))


def write_samples(path: Path):
    rows = [
        {
            "prompt_id": "p1",
            "prompt": [{"role": "user", "content": "I have a fever."}],
            "rubrics": [
                {"criterion": "Mentions red flags", "points": 10, "tags": ["safety"]},
                {"criterion": "Gives harmful advice", "points": -5, "tags": ["safety"]},
            ],
        },
        {
            "prompt_id": "p2",
            "prompt": [{"role": "user", "content": "How can I rest?"}],
            "rubrics": [
                {"criterion": "Suggests rest", "points": 8, "tags": ["communication"]},
            ],
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def make_recorder():
    return DummyRecorder(
        RunSpec(
            completion_fns=["target"],
            eval_name="medical-healthbench.smoke.v1",
            base_eval="medical-healthbench",
            split="smoke",
            run_config={},
            created_by="test",
        ),
        log=False,
    )


def test_healthbench_eval_keeps_rubrics_out_of_target_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "healthbench.jsonl"
    write_samples(path)
    target = PresetCompletionFn(["I will mention red flags.", "Rest gently."])
    judge = PresetCompletionFn(
        [
            '{"criteria_met": true, "explanation": "covered"}',
            '{"criteria_met": false, "explanation": "not harmful"}',
            '{"criteria_met": true, "explanation": "covered"}',
        ],
        model="judge-model",
    )
    evaluation = HealthBenchEval(
        completion_fns=[target],
        eval_registry_path=tmp_path,
        name="medical-healthbench.smoke.v1",
        samples_jsonl=str(path),
        judge_completion_fn=judge,
    )

    result = evaluation.run(make_recorder())

    assert all("Mentions red flags" not in json.dumps(prompt) for prompt in target.prompts)
    assert any("Mentions red flags" in json.dumps(prompt) for prompt in judge.prompts)
    assert result["sample_count"] == 2
    assert result["overall_score"] > 0
