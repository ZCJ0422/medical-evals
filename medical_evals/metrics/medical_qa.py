"""Metrics for closed-ended medical question answering."""

from collections.abc import Sequence

from evals.record import Event


def get_accuracy(events: Sequence[Event]) -> float:
    """Return the fraction of match events marked correct."""
    if not events:
        return 0.0
    return sum(bool(event.data.get("correct")) for event in events) / len(events)


def get_parse_success_rate(events: Sequence[Event]) -> float:
    """Return the fraction of match events with a parsed choice."""
    if not events:
        return 0.0
    return sum(event.data.get("picked") is not None for event in events) / len(events)


accuracy = get_accuracy
parse_success_rate = get_parse_success_rate
