"""P2 Monte-Carlo protocol schema; simulation is intentionally not exposed."""
from __future__ import annotations

from dataclasses import dataclass
from .authorization import Capability, locked_evidence


@dataclass(frozen=True)
class MonteCarloProtocol:
    resamples: int
    status: str = "BUILT_LOCKED"

    def execute(self) -> None:
        if self.resamples < 1:
            raise ValueError("invalid_resample_count")
        locked_evidence(Capability.MONTE_CARLO).require()
