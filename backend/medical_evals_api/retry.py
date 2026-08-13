from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderError(Exception):
    message: str
    retryable: bool = False


class RetryPolicy:
    max_attempts = 3

    def should_retry(self, error: ProviderError, attempt: int) -> bool:
        return error.retryable and attempt < self.max_attempts

    def delay_seconds(self, attempt: int) -> float:
        return float(2 ** max(attempt - 1, 0))
