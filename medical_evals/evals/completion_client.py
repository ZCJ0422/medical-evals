"""Bridge legacy evals completion functions to the shared model-client protocol."""

from medical_evals.core.models import CompletionRequest, ModelResponse


class CompletionFnModelClient:
    def __init__(self, completion_fn, *, model: str | None = None):
        self.completion_fn = completion_fn
        self.model = model or getattr(completion_fn, "model", None)

    def complete(self, request: CompletionRequest, on_event=None) -> ModelResponse:
        if hasattr(self.completion_fn, "complete_core"):
            return self.completion_fn.complete_core(request, on_event=on_event)
        result = self.completion_fn(
            prompt=request.prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        if getattr(result, "error", None) is not None:
            raise result.error
        completions = result.get_completions()
        return ModelResponse(
            text=completions[0] if completions else "",
            model=self.model,
            retry_count=int(getattr(result, "retry_count", 0)),
            raw_response=getattr(result, "raw_data", None),
        )
