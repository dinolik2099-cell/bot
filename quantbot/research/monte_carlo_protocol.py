"""P2 Monte-Carlo protocol schema; simulation is intentionally not exposed."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib, json
from typing import Protocol, Sequence
from .authorization import Capability, locked_evidence


@dataclass(frozen=True)
class MonteCarloProtocol:
    resamples: int
    status: str = "BUILT_LOCKED"

    def execute(self) -> None:
        if self.resamples < 1:
            raise ValueError("invalid_resample_count")
        locked_evidence(Capability.MONTE_CARLO).require()

class TradeResampler(Protocol):
    def resample(self, values: Sequence[float], seed: int) -> Sequence[float]: ...
@dataclass(frozen=True)
class SimulationRequest:
    protocol: MonteCarloProtocol; seed: int; input_identity: str
    def identity(self) -> str: return hashlib.sha256(json.dumps({"resamples": self.protocol.resamples, "seed": self.seed, "input": self.input_identity}, sort_keys=True).encode()).hexdigest()
@dataclass(frozen=True)
class SimulationResult:
    request_identity: str; samples: tuple[float, ...]; synthetic: bool

class DeterministicSyntheticResampler:
    """Unit-test-only resampler; callers still cannot invoke real execution."""
    def resample(self, values: Sequence[float], seed: int) -> Sequence[float]:
        if not values: raise ValueError("samples_required")
        return tuple(values[(seed + index) % len(values)] for index in range(len(values)))

def run_tiny_synthetic(request: SimulationRequest, values: Sequence[float], resampler: TradeResampler) -> SimulationResult:
    if request.protocol.resamples > 8: raise PermissionError("only_tiny_synthetic_mc_allowed")
    return SimulationResult(request.identity(), tuple(float(value) for value in resampler.resample(values, request.seed)), True)
