import json
import re

from medical_evals_api.artifacts import ArtifactWriter


def test_artifact_writer_appends_samples_and_writes_summary(tmp_path):
    writer = ArtifactWriter(tmp_path, "task-1")
    writer.append_sample({"sample_id": "q1", "parse_failed": False})
    writer.log("sample q1 completed")
    writer.write_summary({"accuracy": 0.5, "parse_success_rate": 1.0})

    assert json.loads((tmp_path / "task-1" / "samples.jsonl").read_text().strip()) == {"sample_id": "q1", "parse_failed": False}
    assert "sample q1 completed" in (tmp_path / "task-1" / "run.log").read_text()
    assert json.loads((tmp_path / "task-1" / "summary.json").read_text())["accuracy"] == 0.5


def test_artifact_writer_appends_resume_logs_without_overwriting_previous_run(tmp_path):
    writer = ArtifactWriter(tmp_path, "task-1")
    writer.log("task started")
    writer.log("sample 0 completed")
    writer.log("resuming from checkpoint: 1 samples already completed")
    writer.log("sample 1 completed")

    messages = [
        re.sub(r"^\[[^]]+\] ", "", line)
        for line in (tmp_path / "task-1" / "run.log").read_text(encoding="utf-8").splitlines()
    ]
    assert messages == [
        "task started",
        "sample 0 completed",
        "resuming from checkpoint: 1 samples already completed",
        "sample 1 completed",
    ]


def test_artifact_writer_prefixes_logs_with_local_timezone_timestamp(tmp_path):
    writer = ArtifactWriter(tmp_path, "task-1")
    writer.log("target request completed")

    line = (tmp_path / "task-1" / "run.log").read_text(encoding="utf-8").strip()
    assert re.match(r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\] target request completed$", line)


def test_medqa_result_distinguishes_parse_success_from_accuracy():
    from medical_evals_api.evaluator_adapter import medqa_metrics

    metrics = medqa_metrics([
        {"predicted": "A", "expected": "A", "parse_failed": False},
        {"predicted": "B", "expected": "A", "parse_failed": False},
        {"predicted": None, "expected": "C", "parse_failed": True},
    ])

    assert metrics["parse_success_rate"] == 2 / 3
    assert metrics["accuracy"] == 1 / 3
