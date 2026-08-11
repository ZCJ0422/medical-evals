"""Tests for the Phase 1.1 MedQAEval closed loop."""

import json
from pathlib import Path

import pytest

from evals.base import RunSpec
from evals.record import DummyRecorder, record_sampling
from evals.registry import Registry

from medical_evals.evals.medqa import MedQAEval


class PresetCompletionResult:
    def __init__(self, text):
        self.text = text

    def get_completions(self):
        return [self.text]


class PresetCompletionFn:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []
        self.call_kwargs = []

    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.call_kwargs.append(kwargs)
        return PresetCompletionResult(next(self.responses))


class RecordingPresetCompletionFn(PresetCompletionFn):
    """Test-only model layer that owns the sampling event."""

    def __call__(self, prompt, **kwargs):
        result = super().__call__(prompt, **kwargs)
        sampled = result.get_completions()
        record_sampling(
            prompt=prompt,
            sampled=sampled,
            completion=sampled[0] if sampled else "",
            model="test-model",
            usage={"total_tokens": 3},
        )
        return result


class FailingCompletionFn:
    def __call__(self, prompt, **kwargs):
        raise RuntimeError("simulated rate limit")


class ReportCapturingRecorder(DummyRecorder):
    def __init__(self, run_spec):
        super().__init__(run_spec=run_spec, log=False)
        self.final_reports = []

    def record_final_report(self, final_report):
        self.final_reports.append(final_report)


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def make_sample(question, answer):
    return {
        "question": question,
        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        "answer": answer,
    }


def make_eval(path, completion_fn):
    run_spec = RunSpec(
        completion_fns=["preset"],
        eval_name="medical-medqa.dev.v1",
        base_eval="medical-medqa",
        split="dev",
        run_config={},
        created_by="test",
    )
    recorder = DummyRecorder(run_spec=run_spec, log=False)
    evaluation = MedQAEval(
        completion_fns=[completion_fn],
        eval_registry_path=path.parent,
        name="medical-medqa.dev.v1",
        samples_jsonl=str(path),
    )
    return evaluation, recorder


def test_medqa_eval_records_match_and_accuracy(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C"), make_sample("题目二", "B")])
    # evals uses a deterministic shuffle; the first response is for 题目二.
    completion_fn = PresetCompletionFn(["A", "C"])
    evaluation, recorder = make_eval(path, completion_fn)

    result = evaluation.run(recorder)

    sampling_events = recorder.get_events("sampling")
    match_events = recorder.get_events("match")
    assert len(completion_fn.prompts) == 2
    assert len(sampling_events) == 0
    assert len(match_events) == 2
    assert result["accuracy"] == 0.5
    assert result["parse_success_rate"] == 1.0
    assert "标准答案" not in completion_fn.prompts[0]
    assert "answer" not in completion_fn.prompts[0].lower()


def test_medqa_eval_has_one_sampling_event_per_model_call(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C")])
    evaluation, recorder = make_eval(path, RecordingPresetCompletionFn(["C"]))

    evaluation.run(recorder)

    sampling_events = recorder.get_events("sampling")
    match_events = recorder.get_events("match")
    assert len(sampling_events) == 1
    assert len(match_events) == 1
    assert sampling_events[0].sample_id == match_events[0].sample_id
    assert sampling_events[0].data["model"] == "test-model"
    assert sampling_events[0].data["completion"] == "C"
    assert match_events[0].data["expected"] == "C"
    assert match_events[0].data["picked"] == "C"
    assert match_events[0].data["correct"] is True


def test_medqa_eval_counts_unparseable_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C"), make_sample("题目二", "B")])
    # evals uses a deterministic shuffle; 题目二 is evaluated first.
    evaluation, recorder = make_eval(path, PresetCompletionFn(["无法确定", "C"]))

    result = evaluation.run(recorder)

    assert result["accuracy"] == 0.5
    assert result["parse_success_rate"] == 0.5
    assert any(event.data["picked"] is None for event in recorder.get_events("match"))


def test_medqa_eval_reports_run_duration_and_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C")])
    evaluation, recorder = make_eval(path, PresetCompletionFn(["C"]))

    result = evaluation.run(recorder)

    assert result["status"] == "completed"
    assert result["sample_count"] == 1
    assert result["completed_count"] == 1
    assert result["failed_count"] == 0
    assert result["duration_seconds"] >= 0
    assert result["started_at"]
    assert result["finished_at"]


def test_medqa_eval_reports_model_name(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C")])
    evaluation, recorder = make_eval(path, RecordingPresetCompletionFn(["C"]))

    result = evaluation.run(recorder)

    assert result["model"] == "test-model"


def test_medqa_eval_records_failed_run_duration_before_reraising(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C")])
    run_spec = make_eval(path, FailingCompletionFn())[1].run_spec
    recorder = ReportCapturingRecorder(run_spec)
    evaluation = MedQAEval(
        completion_fns=[FailingCompletionFn()],
        eval_registry_path=path.parent,
        name="medical-medqa.dev.v1",
        samples_jsonl=str(path),
    )

    with pytest.raises(RuntimeError, match="simulated rate limit"):
        evaluation.run(recorder)

    assert len(recorder.final_reports) == 1
    report = recorder.final_reports[0]
    assert report["status"] == "failed"
    assert report["error_type"] == "RuntimeError"
    assert report["duration_seconds"] >= 0
    assert report["completed_count"] == 0


def test_medqa_eval_forwards_configured_generation_parameters(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    path = tmp_path / "samples.jsonl"
    write_jsonl(path, [make_sample("题目一", "C")])
    completion_fn = PresetCompletionFn(["C"])
    evaluation = MedQAEval(
        completion_fns=[completion_fn],
        eval_registry_path=path.parent,
        name="medical-medqa.dev.v1",
        samples_jsonl=str(path),
        temperature=0.2,
        max_tokens=512,
    )

    evaluation.run(make_eval(path, completion_fn)[1])

    assert completion_fn.call_kwargs == [{"temperature": 0.2, "max_tokens": 512}]


def test_registry_loads_medqa_eval_spec():
    registry = Registry([Path("registry")])

    spec = registry.get_eval("medical-medqa.dev.v1")

    assert spec is not None
    assert spec.cls == "medical_evals.evals.medqa:MedQAEval"
    assert spec.args["temperature"] == 0.1
    assert spec.args["max_tokens"] == 2048
    assert spec.args["samples_jsonl"] == "medical_medqa/dev.jsonl"
    eval_factory = registry.get_class(spec)
    assert eval_factory.func is MedQAEval
