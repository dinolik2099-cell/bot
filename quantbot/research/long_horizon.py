"""P2 locked 180/200/240 day target-test state machine.

The specification is intentionally incapable of calculating a result until a
future, separately authorized evaluator supplies a sealed result package.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


WINDOW_DAYS = (180, 200, 240)


@dataclass(frozen=True)
class LongHorizonProtocol:
    initial_equity: float = 10_000.0
    target_equity: float = 90_000.0
    windows: tuple[int, ...] = WINDOW_DAYS
    status: str = "BUILT_LOCKED"

    def validate(self) -> bool:
        if self.status != "BUILT_LOCKED" or self.initial_equity != 10_000.0 or self.target_equity != 90_000.0 or self.windows != WINDOW_DAYS:
            raise ValueError("long_horizon_protocol_drift")
        return True

    def require_authorization(self) -> None:
        raise PermissionError("long_horizon_formal_execution_not_authorized")

class LongHorizonState(str, Enum): PENDING="PENDING"; RUNNING="RUNNING"; INTERRUPTED="INTERRUPTED"; FAILED="FAILED"; COMPLETED="COMPLETED"
@dataclass(frozen=True)
class LongHorizonCheckpoint:
    window_days: int; session: int; state: LongHorizonState; progress_days: int = 0; error: str | None = None
    def resume(self) -> "LongHorizonCheckpoint":
        if self.state not in {LongHorizonState.INTERRUPTED, LongHorizonState.FAILED}: raise ValueError("checkpoint_not_resumable")
        return LongHorizonCheckpoint(self.window_days, self.session + 1, LongHorizonState.RUNNING, self.progress_days)
    def advance(self, observed_days: int) -> "LongHorizonCheckpoint":
        if self.state != LongHorizonState.RUNNING or observed_days <= self.progress_days or observed_days > self.window_days: raise ValueError("invalid_observed_progress")
        return LongHorizonCheckpoint(self.window_days, self.session, LongHorizonState.COMPLETED if observed_days == self.window_days else LongHorizonState.RUNNING, observed_days)
