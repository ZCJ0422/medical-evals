"""HealthBench open-ended evaluation on top of ``evals.Eval``."""

from __future__ import annotations

import random
import time
from collections import defaultdict
from datetime import datetime, timezone

import evals
from evals.record import record_match

from medical_evals.datasets.healthbench import load_healthbench_samples
from medical_evals.judges.rubric import RubricJudge, resolve_judge_completion_fn
from medical_evals.metrics.healthbench import aggregate_samples, aggregate_tag_scores, score_rubrics


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
        self.judge = RubricJudge(
            resolved_judge,
            temperature=judge_temperature,
            max_tokens=judge_max_tokens,
        )

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
        return self._completion_model(self.judge.completion_fn)

    def run(self, recorder):
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
        sample_scores = [{"score": event.data["score"]} for event in match_events]
        by_tag = defaultdict(list)
        for event in match_events:
            for tag, score in event.data.get("tag_scores", {}).items():
                by_tag[tag].append({"score": score})
        result = {
            "overall_score": aggregate_samples(sample_scores),
            "tag_scores": {tag: aggregate_samples(scores) for tag, scores in by_tag.items()},
            "status": "completed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": time.perf_counter() - started_clock,
            "sample_count": len(match_events),
            "completed_count": len(match_events),
            "failed_count": len(recorder.get_events("error")),
            "model": self._model_name(recorder),
            "judge_model": self._judge_model_name(),
        }
        return result

    def eval_sample(self, sample: dict, rng: random.Random):
        del rng
        answer_result = self.completion_fn(
            prompt=build_model_prompt(sample),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        completions = answer_result.get_completions()
        answer = completions[0] if completions else ""

        rubric_results = []
        for rubric in sample["rubrics"]:
            try:
                judgment = self.judge.judge(sample["prompt"], answer, rubric["criterion"])
            except Exception as error:
                judgment = {
                    "criteria_met": False,
                    "explanation": f"judge_error: {error}",
                    "error": type(error).__name__,
                }
            rubric_results.append(
                {
                    "criterion": rubric["criterion"],
                    "points": rubric["points"],
                    "tags": list(rubric.get("tags", [])),
                    **judgment,
                }
            )

        score = score_rubrics(sample["rubrics"], rubric_results)
        tag_scores = aggregate_tag_scores(sample["rubrics"], rubric_results)
        record_match(
            score["score"] >= 0.5,
            expected=None,
            picked=score["score"],
            prompt_id=sample["prompt_id"],
            sampled=answer,
            rubric_results=rubric_results,
            achieved=score["achieved"],
            positive_max=score["positive_max"],
            score=score["score"],
            tag_scores=tag_scores,
        )
        return {
            "prompt_id": sample["prompt_id"],
            "sampled": answer,
            "rubric_results": rubric_results,
            **score,
            "tag_scores": tag_scores,
        }
