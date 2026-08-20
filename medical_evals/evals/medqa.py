"""MedQA CLI evaluation backed by the shared evaluation core."""

import random
import time
from datetime import datetime, timezone

import evals
from evals.record import record_match

from medical_evals.core.medqa import (
    aggregate_medqa,
    build_medqa_prompt,
    evaluate_medqa_sample,
    make_safe_medqa_error,
)
from medical_evals.datasets.medqa import OPTION_KEYS, load_medqa_samples

from .completion_client import CompletionFnModelClient


build_prompt = build_medqa_prompt


class MedQAEval(evals.Eval):
    """Evaluate four-option MedQA samples through the shared core."""

    def __init__(self, *args, temperature: float = 0.1, max_tokens: int = 5120, **kwargs):
        super().__init__(*args, **kwargs)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model_client = CompletionFnModelClient(self.completion_fn)

    def _model_name(self, recorder) -> str | None:
        """Get the actual model from sampling data, with an adapter fallback."""
        for event in recorder.get_events("sampling"):
            model = event.data.get("model")
            if model:
                return str(model)
        model = self.model_client.model
        return str(model) if model else None

    def run(self, recorder):
        started_at = datetime.now(timezone.utc).isoformat()
        started_clock = time.perf_counter()
        try:
            samples = load_medqa_samples(self._get_samples_path())
            sample_results = self.eval_all_samples(recorder, samples, show_progress=False)
        except Exception as error:
            match_events = recorder.get_events("match")
            recorder.record_final_report(
                {
                    "status": "failed",
                    "started_at": started_at,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": time.perf_counter() - started_clock,
                    "sample_count": len(match_events),
                    "completed_count": len(match_events),
                    "failed_count": len(recorder.get_events("error")),
                    "model": self._model_name(recorder),
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
            raise

        summary = aggregate_medqa(sample_results)
        return {
            "accuracy": summary.total_score,
            "parse_success_rate": summary.parse_success_rate,
            "status": "completed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": time.perf_counter() - started_clock,
            "sample_count": summary.total_count,
            "completed_count": summary.total_count,
            "failed_count": summary.failed_count,
            "model": self._model_name(recorder),
        }

    def eval_sample(self, sample: dict, rng: random.Random):
        del rng
        result = evaluate_medqa_sample(
            self.model_client,
            sample,
            model=self.model_client.model or "",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        match_data = {
            "expected": result.expected,
            "picked": result.predicted,
            "sampled": result.raw_output,
            "options": list(OPTION_KEYS),
            "parse_failed": result.parse_failed,
            "retry_count": result.retry_count,
            "error": None,
            "error_category": None,
        }
        if result.error is not None:
            error = make_safe_medqa_error(
                category=result.error.category,
                stage=result.error.stage,
                retry_count=result.error.retry_count,
                status_code=result.error.status_code,
                attempt=result.error.attempt,
            )
            match_data.update(
                {
                    "error": error.message,
                    "error_category": error.category,
                    "error_stage": error.stage,
                    "error_status_code": error.status_code,
                    "error_attempt": error.attempt,
                }
            )
        record_match(result.correct, **match_data)
        return result
