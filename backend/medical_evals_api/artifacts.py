import json
import os
import tempfile
from datetime import datetime
from pathlib import Path


def artifact_root_for_database(database_path: Path) -> Path:
    """Keep task artifacts beside the task database in every runtime mode."""
    return database_path.parent / "artifacts"


class ArtifactWriter:
    def __init__(self, artifact_root: Path, task_id: str):
        self.directory = artifact_root / task_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.samples_path = self.directory / "samples.jsonl"
        self.log_path = self.directory / "run.log"
        self.summary_path = self.directory / "summary.json"
        self.metadata_path = self.directory / "metadata.json"
        self._sample_indexes_are_strictly_increasing = True
        self._last_sample_index: int | None = None
        self._initialize_sample_index_state()

    def append_sample(self, record: dict) -> None:
        with self.samples_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._record_appended_sample(record)

    def _sample_records(self) -> list[dict]:
        if not self.samples_path.exists():
            return []
        records = []
        for line in self.samples_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

    def _initialize_sample_index_state(self) -> None:
        """Allow append only when every persisted record proves the invariant."""
        if not self.samples_path.exists():
            self._set_sample_index_state([])
            return
        records = []
        for line in self.samples_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                self._invalidate_sample_index_state()
                return
            if not isinstance(record, dict):
                self._invalidate_sample_index_state()
                return
            records.append(record)
        self._set_sample_index_state(records)

    def _invalidate_sample_index_state(self) -> None:
        self._sample_indexes_are_strictly_increasing = False
        self._last_sample_index = None

    def _set_sample_index_state(self, records: list[dict]) -> None:
        """Track when an indexed artifact can safely accept an append."""
        previous_index: int | None = None
        for record in records:
            index = record.get("index")
            if (
                not isinstance(index, int)
                or (previous_index is not None and index <= previous_index)
            ):
                self._invalidate_sample_index_state()
                return
            previous_index = index
        self._sample_indexes_are_strictly_increasing = True
        self._last_sample_index = previous_index

    def _record_appended_sample(self, record: dict) -> None:
        index = record.get("index")
        if (
            not self._sample_indexes_are_strictly_increasing
            or not isinstance(index, int)
            or (
                self._last_sample_index is not None
                and index <= self._last_sample_index
            )
        ):
            self._invalidate_sample_index_state()
            return
        self._last_sample_index = index

    def _write_samples_atomically(self, records: list[dict]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=f"{self.samples_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in sorted(records, key=lambda item: item.get("index", 0)):
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.samples_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def upsert_sample(self, record: dict) -> None:
        """Replace a sample record while keeping indexed artifacts ordered."""
        index = record.get("index")
        if not isinstance(index, int):
            self.append_sample(record)
            return
        if (
            self._sample_indexes_are_strictly_increasing
            and (self._last_sample_index is None or index > self._last_sample_index)
        ):
            self.append_sample(record)
            return
        indexed = {
            existing_index: existing
            for existing in self._sample_records()
            if isinstance(existing_index := existing.get("index"), int)
        }
        indexed[index] = record
        ordered_records = sorted(indexed.values(), key=lambda item: item.get("index", 0))
        self._write_samples_atomically(ordered_records)
        self._set_sample_index_state(ordered_records)

    def load_checkpoint(self) -> dict[int, dict]:
        """Return successful sample records that are safe to resume from."""
        if not self.samples_path.exists():
            return {}
        latest: dict[int, dict] = {}
        for line in self.samples_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or record.get("error"):
                continue
            index = record.get("index")
            if isinstance(index, int):
                latest[index] = record
        return latest

    def rewrite_samples(self, records: list[dict]) -> None:
        """Compact checkpoint records before a resumed run appends new samples."""
        ordered_records = sorted(records, key=lambda item: item.get("index", 0))
        self._write_samples_atomically(ordered_records)
        self._set_sample_index_state(ordered_records)

    def log(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            handle.write(f"[{timestamp}] {message.rstrip()}\n")
            handle.flush()

    def write_summary(self, summary: dict) -> None:
        self.summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def write_metadata(self, metadata: dict) -> None:
        """Write reproducibility metadata without credentials or raw secrets."""
        self.metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
