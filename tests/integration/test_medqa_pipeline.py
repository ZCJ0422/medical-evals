"""End-to-end MedQA pipeline tests using a fake OpenAI-compatible client."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import evals.eval as eval_module
import httpx
from evals.base import RunSpec
from evals.cli import oaieval
from evals.record import DummyRecorder
from evals.registry import Registry
from openai import APIStatusError
from medical_evals.adapters import OpenAICompatibleCompletionFn
from medical_evals.core.models import CompletionRequest, EvaluationEvent, ModelResponse
from medical_evals.evals import MedQAEval


class FakeChatCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeOpenAIClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(response))


class CoreOnlyCompletionFn:
    model = "core-only-model"

    def __init__(self):
        self.requests = []

    def __call__(self, prompt, **kwargs):
        raise AssertionError("legacy completion call should not be used")

    def complete_core(self, request: CompletionRequest, on_event=None) -> ModelResponse:
        self.requests.append(request)
        if on_event is not None:
            on_event(EvaluationEvent(kind="retry", stage="request", attempt=1))
        return ModelResponse(text="C", model=self.model, retry_count=1)


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
        temperature=0.2,
        max_tokens=512,
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
    assert sampling_data["request_metadata"] == {"temperature": 0.2, "max_tokens": 512}
    assert isinstance(sampling_data["latency"], float)
    assert sampling_data["latency"] >= 0

    match_data = match_events[0].data
    assert match_data["expected"] == "C"
    assert match_data["picked"] == "C"
    assert match_data["correct"] is True
    assert match_data["sampled"] == "C"
    assert result["accuracy"] == 1.0
    assert result["parse_success_rate"] == 1.0


def test_medqa_pipeline_prefers_the_shared_completion_client(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    dataset_path = tmp_path / "medqa.jsonl"
    write_medqa_sample(dataset_path)
    completion_fn = CoreOnlyCompletionFn()
    evaluation = MedQAEval(
        completion_fns=[completion_fn],
        eval_registry_path=tmp_path,
        name="medical-medqa.dev.v1",
        samples_jsonl=str(dataset_path),
        temperature=0.2,
        max_tokens=512,
    )

    result = evaluation.run(make_recorder())

    assert len(completion_fn.requests) == 1
    assert completion_fn.requests[0].temperature == 0.2
    assert completion_fn.requests[0].max_tokens == 512
    assert result["accuracy"] == 1.0
    assert result["model"] == "core-only-model"


def test_medqa_cli_recorder_and_match_redact_provider_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALS_SEQUENTIAL", "1")
    dataset_path = tmp_path / "medqa.jsonl"
    write_medqa_sample(dataset_path)
    api_key = "redaction-cli-api-key"
    userinfo = "redaction-cli-userinfo"
    provider_body = "redaction-cli-provider-body"
    secrets = (api_key, userinfo, provider_body)
    provider_error = APIStatusError(
        "Authorization: Bearer redaction-cli-api-key; "
        "url=https://alice:redaction-cli-userinfo@example.test/callback; "
        "provider_body=redaction-cli-provider-body",
        response=httpx.Response(
            401,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
        ),
        body={"error": {"message": provider_body}},
    )
    completion_fn = OpenAICompatibleCompletionFn(
        api_key=api_key,
        model="fake-medical-model",
        client=FakeOpenAIClient(provider_error),
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

    assert result["failed_count"] == 1
    persisted_events = [
        event.data
        for event_type in ("error", "match")
        for event in recorder.get_events(event_type)
    ]
    assert all(secret not in str(event) for secret in secrets for event in persisted_events)
    match = recorder.get_events("match")[0].data
    assert match["error"] == "request failed: authentication_error"
    assert match["error_category"] == "authentication_error"
    assert match["error_stage"] == "request"
    assert match["error_status_code"] == 401
    assert match["error_attempt"] == 1


def test_registry_loads_medqa_pipeline_definition():
    registry = Registry([Path("registry")])

    spec = registry.get_eval("medical-medqa.dev.v1")

    assert spec is not None
    assert spec.cls == "medical_evals.evals.medqa:MedQAEval"
    eval_factory = registry.get_class(spec)
    assert eval_factory.func is MedQAEval


def test_external_cli_exposes_project_registry_option():
    parser = oaieval.get_parser()
    args = parser.parse_args(
        ["medical-openai-compatible", "medical-medqa.dev.v1", "--registry_path", "registry"]
    )

    assert args.registry_path == ["registry"]


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
        "medical_evals.core.openai_compatible.OpenAI",
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
        run_id = oaieval.run(args, registry=Registry([Path("registry")]))
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
