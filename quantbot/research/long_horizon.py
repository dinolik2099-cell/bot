"""P2 locked 180/200/240 day target-test state machine.

The specification is intentionally incapable of calculating a result until a
future, separately authorized evaluator supplies a sealed result package.
"""
from __future__ import annotations

from dataclasses import dataclass


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
