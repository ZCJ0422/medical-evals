export type TaskStatus = "queued" | "running" | "completed" | "partial_failed" | "failed" | "cancelled";

export type TaskSummary = {
  task_id: string;
  name: string;
  target_model_id: string;
  judge_model_id: string;
  dataset_version_id: string;
  status: TaskStatus;
  progress: { completed_count: number; total_count: number; progress_percent: number; success_count: number; failed_count: number; retry_count: number; stage: string };
  created_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
};

export type DatasetVersion = {
  dataset_version_id: string;
  dataset_id: string;
  rubric_id: string;
  name: string;
  version: string;
  sample_count: number;
};
