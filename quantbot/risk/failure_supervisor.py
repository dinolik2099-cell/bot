"""Deterministic failure supervisor with no authority to place orders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FailureSupervisorDecision:
    allowed: bool
    reason: str
    consecutive_failures: int


def supervise_failures(events: Iterable[str], *, max_consecutive_failures: int = 3) -> FailureSupervisorDecision:
    if max_consecutive_failures < 1:
        raise ValueError("invalid_failure_threshold")
    streak = 0
    for event in events:
        streak = streak + 1 if event == "FAILED" else 0
    return FailureSupervisorDecision(streak < max_consecutive_failures,
                                     "ok" if streak < max_consecutive_failures else "failure_circuit_open", streak)
