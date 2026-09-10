"""P2 Monte-Carlo protocol schema and deterministic non-OOS resampling rules."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib, json
from typing import Mapping, Protocol, Sequence
from .authorization import Capability, locked_evidence
from .artifact_store import seal, validate_seal


@dataclass(frozen=True)
class MonteCarloProtocol:
    resamples: int
    status: str = "BUILT_LOCKED"

    def execute(self) -> None:
        self.validate()
        locked_evidence(Capability.MONTE_CARLO).require()

    def validate(self) -> bool:
        if not isinstance(self.resamples,int) or self.resamples < 1 or self.status != "BUILT_LOCKED":
            raise ValueError("monte_carlo_protocol_invalid")
        return True

class TradeResampler(Protocol):
    def resample(self, values: Sequence[float], seed: int) -> Sequence[float]: ...
@dataclass(frozen=True)
class SimulationRequest:
    protocol: MonteCarloProtocol; seed: int; input_identity: str
    def identity(self) -> str:
        self.protocol.validate()
        if not isinstance(self.seed,int) or not isinstance(self.input_identity,str) or not self.input_identity: raise ValueError("simulation_request_invalid")
        return hashlib.sha256(json.dumps({"schema_version":"quantbot-monte-carlo-request-v1","resamples":self.protocol.resamples,"status":self.protocol.status,"seed":self.seed,"input":self.input_identity},sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True)
class SimulationResult:
    request_identity: str; samples: tuple[float, ...]; synthetic: bool

def build_synthetic_result_artifact(request: SimulationRequest, result: SimulationResult) -> dict[str, object]:
    """Seal only a tiny synthetic fixture; formal Monte Carlo remains locked."""
    if not result.synthetic or result.request_identity!=request.identity(): raise ValueError('synthetic_mc_result_binding_invalid')
    if request.protocol.resamples>8 or len(result.samples)==0: raise ValueError('synthetic_mc_result_not_allowed')
    return seal({'schema_version':'quantbot-monte-carlo-synthetic-result-v1','request_identity':result.request_identity,
                 'samples':[float(value) for value in result.samples],'synthetic':True,
                 'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})

def validate_synthetic_result_artifact(artifact: Mapping[str, object], *, request: SimulationRequest) -> bool:
    validate_seal(artifact)
    if artifact.get('schema_version')!='quantbot-monte-carlo-synthetic-result-v1' or artifact.get('request_identity')!=request.identity() or artifact.get('synthetic') is not True:
        raise ValueError('synthetic_mc_artifact_binding_invalid')
    if artifact.get('oos_status')!='SEALED' or artifact.get('oos_authorization')!='NOT_AUTHORIZED' or request.protocol.resamples>8:
        raise ValueError('synthetic_mc_artifact_oos_invalid')
    samples=artifact.get('samples')
    if not isinstance(samples,list) or not samples or any(not isinstance(value,(int,float)) for value in samples): raise ValueError('synthetic_mc_artifact_samples_invalid')
    return True

class DeterministicSyntheticResampler:
    """Unit-test-only resampler; callers still cannot invoke real execution."""
    def resample(self, values: Sequence[float], seed: int) -> Sequence[float]:
        if not values: raise ValueError("samples_required")
        return tuple(values[(seed + index) % len(values)] for index in range(len(values)))

def run_tiny_synthetic(request: SimulationRequest, values: Sequence[float], resampler: TradeResampler) -> SimulationResult:
    request.protocol.validate(); request.identity()
    if request.protocol.resamples > 8: raise PermissionError("only_tiny_synthetic_mc_allowed")
    return SimulationResult(request.identity(), tuple(float(value) for value in resampler.resample(values, request.seed)), True)
