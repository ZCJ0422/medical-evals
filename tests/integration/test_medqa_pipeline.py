"""End-to-end MedQA pipeline tests using a fake OpenAI-compatible client."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import evals.eval as eval_module
from evals.base import RunSpec
from evals.cli import oaieval
from evals.record import DummyRecorder
from evals.registry import Registry
from medical_evals.adapters import OpenAICompatibleCompletionFn
from medical_evals.evals import MedQAEval


class FakeChatCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(response))


def write_medqa_sample(path: Path) -> None:
    sample = {
        "question": "患者出现发热，最常用的体温测量部位是什么？",
        "options": {
            "A": "皮肤",
            "B": "眼睛",
            "C": "口腔",
            "D": "头发",
        },
        "answer": "C",
    }
    path.write_text(json.dumps(sample, ensure_ascii=False) + "\n", encoding="utf-8")


def make_recorder() -> DummyRecorder:
    run_spec = RunSpec(
        completion_fns=["fake-openai"],
        eval_name="medical-medqa.dev.v1",
        base_eval="medical-medqa",
        split="dev",
        run_config={},
        created_by="integration-test",
    )
    return DummyRecorder(run_spec=run_spec, log=False)


def test_medqa_pipeline_records_one_sampling_and_one_match(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    dataset_path = tmp_path / "medqa.jsonl"
    write_medqa_sample(dataset_path)

    fake_response = SimpleNamespace(
        model="fake-medical-model",
        usage=SimpleNamespace(prompt_tokens=32, completion_tokens=1, total_tokens=33),
        choices=[SimpleNamespace(message=SimpleNamespace(content="C"))],
    )
    fake_client = FakeOpenAIClient(fake_response)
    completion_fn = OpenAICompatibleCompletionFn(
        model="fake-medical-model",
        client=fake_client,
        max_retries=0,
    )
    recorder = make_recorder()
    evaluation = MedQAEval(
        completion_fns=[completion_fn],
        eval_registry_path=tmp_path,
        name="medical-medqa.dev.v1",
        samples_jsonl=str(dataset_path),
    )

    result = evaluation.run(recorder)

    sampling_events = recorder.get_events("sampling")
    match_events = recorder.get_events("match")
    assert len(fake_client.chat.completions.calls) == 1
    assert len(sampling_events) == 1
    assert len(match_events) == 1
    assert sampling_events[0].sample_id == match_events[0].sample_id

    sampling_data = sampling_events[0].data
    assert sampling_data["prompt"]
    assert sampling_data["completion"] == "C"
    assert sampling_data["model"] == "fake-medical-model"
    assert sampling_data["usage"] == {
        "prompt_tokens": 32,
        "completion_tokens": 1,
        "total_tokens": 33,
    }
    assert isinstance(sampling_data["latency"], float)
    assert sampling_data["latency"] >= 0

    match_data = match_events[0].data
    assert match_data["expected"] == "C"
    assert match_data["picked"] == "C"
    assert match_data["correct"] is True
    assert match_data["sampled"] == "C"
    assert result["accuracy"] == 1.0
    assert result["parse_success_rate"] == 1.0


def test_registry_loads_medqa_pipeline_definition():
    registry = Registry([Path("evals/registry")])

    spec = registry.get_eval("medical-medqa.dev.v1")

    assert spec is not None
    assert spec.cls == "medical_evals.evals.medqa:MedQAEval"
    eval_factory = registry.get_class(spec)
    assert eval_factory.func is MedQAEval


def test_default_run_paths_include_eval_model_and_run_id(tmp_path):
    record_path, log_path = oaieval.default_run_paths(
        "medical-medqa.dev.v1",
        "MiniMax-M3",
        "260807075935BR53HO76",
        root=tmp_path,
    )

    assert record_path == str(
        tmp_path / "medical-medqa.dev.v1__MiniMax-M3__260807075935BR53HO76.jsonl"
    )
    assert log_path == str(
        tmp_path / "medical-medqa.dev.v1__MiniMax-M3__260807075935BR53HO76.log"
    )


def test_oaieval_runner_loads_registered_completion_fn(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    monkeypatch.setenv("OPENAI_MODEL", "fake-medical-model")
    fake_response = SimpleNamespace(
        model="fake-medical-model",
        usage=SimpleNamespace(prompt_tokens=32, completion_tokens=1, total_tokens=33),
        choices=[SimpleNamespace(message=SimpleNamespace(content="C"))],
    )
    fake_client = FakeOpenAIClient(fake_response)
    monkeypatch.setattr(
        "medical_evals.adapters.openai_compatible.OpenAI",
        lambda **_: fake_client,
    )

    captured = {}

    def build_test_recorder(args, run_spec, record_path):
        captured["recorder"] = DummyRecorder(run_spec=run_spec, log=False)
        return captured["recorder"]

    monkeypatch.setattr(oaieval, "build_recorder", build_test_recorder)
    args = oaieval.get_parser().parse_args(
        [
            "medical-openai-compatible",
            "medical-medqa.dev.v1",
            "--max_samples",
            "1",
            "--extra_eval_params",
            "temperature=0.2,max_tokens=512",
            "--record_path",
            str(tmp_path / "smoke.jsonl"),
            "--log_to_file",
            str(tmp_path / "smoke.log"),
            "--local-run",
        ]
    )

    previous_max_samples = eval_module._MAX_SAMPLES
    try:
        run_id = oaieval.run(args, registry=Registry([Path("evals/registry")]))
    finally:
        eval_module.set_max_samples(previous_max_samples)

    recorder = captured["recorder"]
    assert run_id == recorder.run_spec.run_id
    assert recorder.run_spec.eval_name == "medical-medqa.dev.v1"
    assert recorder.run_spec.created_at
    assert recorder.run_spec.completion_fns == ["medical-openai-compatible"]
    assert (
        recorder.run_spec.run_config["eval_spec"].args["samples_jsonl"]
        == "medical_medqa/dev.jsonl"
    )
    assert len(recorder.get_events("sampling")) == 1
    assert len(recorder.get_events("match")) == 1
    assert recorder.get_events("sampling")[0].sample_id == recorder.get_events("match")[0].sample_id
    assert recorder.get_events("sampling")[0].data["model"] == "fake-medical-model"
    assert fake_client.chat.completions.calls[0]["temperature"] == 0.2
    assert fake_client.chat.completions.calls[0]["max_tokens"] == 512
