"""Minimal MedQA evaluation implemented on top of ``evals.Eval``."""

import random
import time
from datetime import datetime, timezone

import evals
from evals.record import record_match

from medical_evals.datasets.medqa import OPTION_KEYS, load_medqa_samples
from medical_evals.graders.choice_parser import parse_choice
from medical_evals.metrics.medical_qa import get_accuracy, get_parse_success_rate


def build_prompt(sample: dict) -> str:
    """Build a MedQA prompt without exposing the reference answer."""
    lines = [
        "请回答下面的医学单项选择题。",
        f"题目：{sample['question']}",
        "选项：",
    ]
    lines.extend(f"{key}. {sample['options'][key]}" for key in OPTION_KEYS)
    lines.extend(
        [
            "要求：",
            "不要输出解释、推理过程、答案文字、标点符号、Markdown 或其他内容。",
            "请只输出一个选项字母（A、B、C 或 D）。",
        ]
    )
    return "\n".join(lines)


class MedQAEval(evals.Eval):
    """Evaluate a model on four-option MedQA samples."""

    def __init__(self, *args, temperature: float = 0.1, max_tokens: int = 2048, **kwargs):
        super().__init__(*args, **kwargs)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _model_name(self, recorder) -> str | None:
        """Get the actual model from sampling data, with an adapter fallback."""
        for event in recorder.get_events("sampling"):
            model = event.data.get("model")
            if model:
                return str(model)
        model = getattr(self.completion_fn, "model", None)
        return str(model) if model else None

    def run(self, recorder):
        started_at = datetime.now(timezone.utc).isoformat()
        started_clock = time.perf_counter()
        try:
            samples = load_medqa_samples(self._get_samples_path())
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
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
            raise

        match_events = recorder.get_events("match")
        return {
            "accuracy": get_accuracy(match_events),
            "parse_success_rate": get_parse_success_rate(match_events),
            "status": "completed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": time.perf_counter() - started_clock,
            "sample_count": len(match_events),
            "completed_count": len(match_events),
            "failed_count": len(recorder.get_events("error")),
            "model": self._model_name(recorder),
        }

    def eval_sample(self, sample: dict, rng: random.Random):
        del rng
        prompt = build_prompt(sample)
        result = self.completion_fn(
            prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        completions = result.get_completions()
        sampled = completions[0] if completions else ""
        picked = parse_choice(sampled)

        record_match(
            picked == sample["answer"],
            expected=sample["answer"],
            picked=picked,
            sampled=sampled,
            options=list(OPTION_KEYS),
        )
        return {"picked": picked, "correct": picked == sample["answer"]}
