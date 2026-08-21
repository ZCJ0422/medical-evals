import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  target_model_id TEXT NOT NULL,
  judge_model_id TEXT NOT NULL,
  dataset_version_id TEXT NOT NULL,
  rubric_id TEXT NOT NULL,
  status TEXT NOT NULL,
  progress_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  error TEXT,
  target_base_url TEXT NOT NULL DEFAULT '',
  target_api_key_env TEXT NOT NULL DEFAULT '',
  judge_base_url TEXT NOT NULL DEFAULT '',
  judge_api_key_env TEXT NOT NULL DEFAULT '',
  max_samples INTEGER,
  target_api_key_enc TEXT NOT NULL DEFAULT '',
  judge_api_key_enc TEXT NOT NULL DEFAULT '',
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS task_results (
  task_id TEXT PRIMARY KEY,
  total_score REAL NOT NULL DEFAULT 0,
  dimension_scores_json TEXT NOT NULL DEFAULT '{}',
  error_categories_json TEXT NOT NULL DEFAULT '{}',
  completed_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  accuracy REAL,
  parse_success_rate REAL,
  request_success_count INTEGER NOT NULL DEFAULT 0,
  parse_failed_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
    for name in ("target_base_url", "target_api_key_env", "judge_base_url", "judge_api_key_env"):
        if name not in columns:
            connection.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    if "max_samples" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN max_samples INTEGER")
    for name in ("target_api_key_enc", "judge_api_key_enc"):
        if name not in columns:
            connection.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    for name in ("lease_owner", "lease_expires_at"):
        if name not in columns:
            connection.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    result_columns = {row["name"] for row in connection.execute("PRAGMA table_info(task_results)")}
    for name, definition in (("accuracy", "REAL"), ("parse_success_rate", "REAL"), ("request_success_count", "INTEGER NOT NULL DEFAULT 0"), ("parse_failed_count", "INTEGER NOT NULL DEFAULT 0")):
        if name not in result_columns:
            connection.execute(f"ALTER TABLE task_results ADD COLUMN {name} {definition}")
    return connection
