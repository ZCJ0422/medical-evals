import json
import re

import pytest

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


def test_medqa_checkpoint_records_use_shared_aggregation():
    from medical_evals.core.medqa import aggregate_medqa
    from medical_evals_api.evaluator_adapter import deserialize_medqa_record

    records = [
        {"sample_id": "1", "predicted": "A", "expected": "A", "correct": True, "parse_failed": False, "raw_output": "A", "error": None, "retry_count": 0},
        {"sample_id": "2", "predicted": "B", "expected": "A", "correct": False, "parse_failed": False, "raw_output": "B", "error": None, "retry_count": 0},
        {"sample_id": "3", "predicted": None, "expected": "C", "correct": False, "parse_failed": True, "raw_output": "?", "error": None, "retry_count": 0},
    ]

    metrics = aggregate_medqa([deserialize_medqa_record(record) for record in records])

    assert metrics.parse_success_rate == 2 / 3
    assert metrics.total_score == 1 / 3


def test_artifact_writer_appends_strictly_increasing_indices_without_atomic_rewrite(
    tmp_path, monkeypatch
):
    writer = ArtifactWriter(tmp_path, "task-1")

    def fail_atomic_rewrite(*_args, **_kwargs):
        raise AssertionError("strictly increasing samples must use append persistence")

    monkeypatch.setattr(writer, "_write_samples_atomically", fail_atomic_rewrite)
    writer.upsert_sample({"index": 0, "sample_id": "sample-0"})
    writer.upsert_sample({"index": 1, "sample_id": "sample-1"})

    records = [
        json.loads(line)
        for line in writer.samples_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["index"] for record in records] == [0, 1]


def test_artifact_writer_rewrites_a_nonempty_malformed_artifact_before_upsert(
    tmp_path, monkeypatch
):
    directory = tmp_path / "task-1"
    directory.mkdir()
    (directory / "samples.jsonl").write_text("not-json\n", encoding="utf-8")
    writer = ArtifactWriter(tmp_path, "task-1")
    atomic_writes = []
    write_atomically = writer._write_samples_atomically

    def record_atomic_write(records):
        atomic_writes.append(records)
        write_atomically(records)

    monkeypatch.setattr(writer, "_write_samples_atomically", record_atomic_write)
    writer.upsert_sample({"index": 0, "sample_id": "sample-0"})

    assert len(atomic_writes) == 1
    assert writer.samples_path.read_text(encoding="utf-8") == (
        '{"index": 0, "sample_id": "sample-0"}\n'
    )


@pytest.mark.parametrize(
    ("existing_records", "new_record", "expected_indices", "expected_sample_ids"),
    [
        (
            [{"index": 0, "sample_id": "old-0"}],
            {"index": 0, "sample_id": "new-0"},
            [0],
            ["new-0"],
        ),
        (
            [{"index": 1, "sample_id": "sample-1"}],
            {"index": 0, "sample_id": "sample-0"},
            [0, 1],
            ["sample-0", "sample-1"],
        ),
    ],
    ids=("duplicate-index", "earlier-sparse-index"),
)
def test_artifact_writer_atomically_rewrites_duplicate_or_earlier_indices(
    tmp_path,
    monkeypatch,
    existing_records,
    new_record,
    expected_indices,
    expected_sample_ids,
):
    writer = ArtifactWriter(tmp_path, "task-1")
    for record in existing_records:
        writer.append_sample(record)

    atomic_writes = []
    write_atomically = writer._write_samples_atomically

    def record_atomic_write(records):
        atomic_writes.append(records)
        write_atomically(records)

    monkeypatch.setattr(writer, "_write_samples_atomically", record_atomic_write)
    writer.upsert_sample(new_record)

    records = [
        json.loads(line)
        for line in writer.samples_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(atomic_writes) == 1
    assert [record["index"] for record in records] == expected_indices
    assert [record["sample_id"] for record in records] == expected_sample_ids
