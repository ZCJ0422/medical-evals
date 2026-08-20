"""HealthBench open-ended evaluation on top of ``evals.Eval``."""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone

import evals
from evals.record import record_match

from medical_evals.datasets.healthbench import load_healthbench_samples
from medical_evals.core.healthbench import (
    aggregate_healthbench,
    build_healthbench_prompt,
    evaluate_healthbench_sample,
)
from medical_evals.evals.completion_client import CompletionFnModelClient
from medical_evals.judges.rubric import resolve_judge_completion_fn


def build_model_prompt(sample: dict) -> list[dict]:
    """Return only the conversation shown to the evaluated model."""
    return [dict(message) for message in sample["prompt"]]


class HealthBenchEval(evals.Eval):
    """Evaluate open-ended medical answers against HealthBench rubrics."""

    def __init__(
        self,
        *args,
        temperature: float = 0.1,
        max_tokens: int = 5120,
        judge_completion_fn=None,
        judge_model: str | None = None,
        judge_temperature: float = 0.0,
        judge_max_tokens: int = 5120,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.judge_model = judge_model
        self.judge_temperature = judge_temperature
        self.judge_max_tokens = judge_max_tokens
        if judge_completion_fn is None:
            resolved_judge = self.completion_fn
        else:
            resolved_judge = resolve_judge_completion_fn(judge_completion_fn, self.registry)
        self.judge_completion_fn = resolved_judge
        self.model_client = CompletionFnModelClient(self.completion_fn)
        self.judge_client = CompletionFnModelClient(resolved_judge, model=judge_model)
        self._sample_results = []

    @staticmethod
    def _completion_model(completion_fn) -> str | None:
        model = getattr(completion_fn, "model", None)
        return str(model) if model else None

    def _model_name(self, recorder) -> str | None:
        for event in recorder.get_events("sampling"):
            model = event.data.get("model")
            if model:
                return str(model)
        return self._completion_model(self.completion_fn)

    def _judge_model_name(self) -> str | None:
        if self.judge_model:
            return self.judge_model
        return self._completion_model(self.judge_completion_fn)

    def run(self, recorder):
        self._sample_results = []
        started_at = datetime.now(timezone.utc).isoformat()
        started_clock = time.perf_counter()
        try:
            samples = load_healthbench_samples(self._get_samples_path())
            self.eval_all_samples(recorder, samples, show_progress=False)
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
                    "judge_model": self._judge_model_name(),
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
            raise

        match_events = recorder.get_events("match")
        summary = aggregate_healthbench(self._sample_results)
        result = {
            "overall_score": summary.total_score,
            "tag_scores": {key.removeprefix("tag:"): value for key, value in summary.dimensions.items() if key.startswith("tag:")},
            "status": "completed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": time.perf_counter() - started_clock,
            "sample_count": len(match_events),
            "completed_count": len(match_events),
            "failed_count": summary.failed_count,
            "model": self._model_name(recorder),
            "judge_model": self._judge_model_name(),
        }
        return result

    def eval_sample(self, sample: dict, rng: random.Random):
        del rng
        result = evaluate_healthbench_sample(
            self.model_client,
            self.judge_client,
            sample,
            target_model=self.model_client.model or "",
            judge_model=self._judge_model_name() or "",
            target_temperature=self.temperature,
            target_max_tokens=self.max_tokens,
            judge_temperature=self.judge_temperature,
            judge_max_tokens=self.judge_max_tokens,
        )
        self._sample_results.append(result)
        answer = result.raw_output
        rubric_results = list(result.rubric_judgments)
        record_match(
            result.error is None and (result.score or 0.0) >= 0.5,
            expected=None,
            picked=result.score or 0.0,
            prompt_id=sample["prompt_id"],
            sampled=answer,
            rubric_results=rubric_results,
            achieved=result.achieved or 0.0,
            positive_max=result.positive_max or 0.0,
            score=result.score or 0.0,
            tag_scores=result.tag_scores,
            error=result.error.message if result.error else None,
            error_category=result.error.category if result.error else None,
        )
        return result
