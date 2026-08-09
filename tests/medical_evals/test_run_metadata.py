"""Tests for medical evaluation run metadata models and JSON reports."""

import json
from pathlib import Path

from evals.base import RunSpec
from evals.record import DummyRecorder, record_sampling
from medical_evals.models import ModelSpec
from medical_evals.reports import EvalRunMetadata, write_run_metadata


def make_run_spec() -> RunSpec:
    return RunSpec(
        completion_fns=["medical-openai-compatible"],
        eval_name="medical-medqa.dev.v1",
        base_eval="medical-medqa",
        split="dev",
        run_config={"dataset": "medqa.dev.v1"},
        created_by="test",
    )


def test_model_spec_serializes_provider_and_parameters():
    model = ModelSpec(
        model_id="medical-model",
        provider="openai-compatible",
        version="2026-08-07",
        endpoint="https://example.test/v1",
        parameters={"temperature": 0.0, "max_tokens": 1},
    )

    assert model.to_dict() == {
        "model_id": "medical-model",
        "provider": "openai-compatible",
        "version": "2026-08-07",
        "endpoint": "https://example.test/v1",
        "parameters": {"temperature": 0.0, "max_tokens": 1},
    }


def test_run_metadata_can_be_created_from_run_spec():
    run_spec = make_run_spec()
    model = ModelSpec(model_id="medical-model", provider="openai-compatible")

    metadata = EvalRunMetadata.from_run_spec(
        run_spec,
        dataset_version="medqa.dev.v1",
        model_spec=model,
        prompt_version="medqa.prompt.v1",
        grader_version="choice-grader.v1",
    )

    assert metadata.eval_id == "medical-medqa.dev.v1"
    assert metadata.dataset_version == "medqa.dev.v1"
    assert metadata.model_spec == model
    assert metadata.prompt_version == "medqa.prompt.v1"
    assert metadata.grader_version == "choice-grader.v1"
    assert metadata.timestamp == run_spec.created_at
    assert metadata.run_id == run_spec.run_id


def test_run_metadata_writes_json(tmp_path):
    metadata = EvalRunMetadata(
        eval_id="medical-medqa.dev.v1",
        dataset_version="medqa.dev.v1",
        model_spec=ModelSpec(model_id="medical-model", provider="openai-compatible"),
        prompt_version="medqa.prompt.v1",
        grader_version="choice-grader.v1",
        timestamp="2026-08-07T12:00:00+00:00",
        run_id="run-123",
    )
    output_path = tmp_path / "reports" / "run_metadata.json"

    written_path = write_run_metadata(metadata, output_path)

    assert written_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["eval_id"] == "medical-medqa.dev.v1"
    assert payload["dataset_version"] == "medqa.dev.v1"
    assert payload["model_spec"]["model_id"] == "medical-model"
    assert payload["timestamp"] == "2026-08-07T12:00:00+00:00"
    assert payload["run_id"] == "run-123"


def test_run_metadata_associates_sampling_event_by_run_id():
    run_spec = make_run_spec()
    recorder = DummyRecorder(run_spec=run_spec, log=False)
    metadata = EvalRunMetadata.from_run_spec(
        run_spec,
        dataset_version="medqa.dev.v1",
        model_spec=ModelSpec(model_id="medical-model", provider="openai-compatible"),
        prompt_version="medqa.prompt.v1",
        grader_version="choice-grader.v1",
    )

    with recorder.as_default_recorder("medical-medqa.dev.0"):
        record_sampling(
            prompt="题目",
            sampled=["C"],
            completion="C",
            model="medical-model",
            usage={"total_tokens": 1},
            latency=0.1,
        )

    sampling_event = recorder.get_events("sampling")[0]

    assert metadata.matches_sampling_event(sampling_event)
    assert sampling_event.run_id == metadata.run_id
