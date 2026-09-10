"""Canonical, sealed non-OOS Monte-Carlo execution orchestration."""
from __future__ import annotations
import random
from typing import Any, Mapping, Sequence
from .authorization import Capability, AuthorizationEvidence, locked_evidence
from .artifact_store import seal, validate_seal
from .future_data_plane import FutureRuntimeContext
from .future_stage_execution import _execute_verified_chunks
from .monte_carlo_protocol import MonteCarloProtocol


class MonteCarloRunnerError(RuntimeError):
    pass


def build_monte_carlo_execution_request(*, runtime: FutureRuntimeContext) -> dict[str,object]:
    """Validate the frozen request before any upstream evidence is accessed."""
    runtime.validate()
    if runtime.protocol.get('stage')!='monte_carlo': raise MonteCarloRunnerError('monte_carlo_stage_required')
    config=runtime.protocol.get('config')
    if not isinstance(config,Mapping): raise MonteCarloRunnerError('monte_carlo_config_missing')
    try: protocol=MonteCarloProtocol(**dict(config.get('protocol',{})))
    except (TypeError,ValueError) as exc: raise MonteCarloRunnerError('monte_carlo_protocol_invalid') from exc
    protocol.validate()
    if config.get('execution_mode')!='FORMAL_LOCKED': raise MonteCarloRunnerError('monte_carlo_execution_mode_invalid')
    return {'protocol_identity':runtime.protocol['artifact_identity'],'execution_plan_identity':runtime.plan['artifact_identity'],
            'input_identity':runtime.input_identity,'resamples':protocol.resamples,
            'execution_mode':'FORMAL_LOCKED','oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'}


def require_monte_carlo_execution_authority(request: Mapping[str,object]) -> None:
    """Preserve the separate locked MC capability boundary."""
    if request.get('execution_mode')!='FORMAL_LOCKED' or request.get('oos_status')!='SEALED' or request.get('oos_authorization')!='NOT_AUTHORIZED':
        raise MonteCarloRunnerError('monte_carlo_request_invalid')
    locked_evidence(Capability.MONTE_CARLO).require()


def _validated_upstream_returns(artifact: Mapping[str, Any], *, runtime: FutureRuntimeContext) -> tuple[float, ...]:
    """Accept only a sealed, non-synthetic upstream T/V evidence artifact."""
    validate_seal(artifact)
    if artifact.get('synthetic') is True or artifact.get('formal_result') is not True:
        raise MonteCarloRunnerError('monte_carlo_synthetic_upstream_forbidden')
    for key, expected in (('research_freeze_identity', runtime.protocol.get('config', {}).get('research_freeze_identity')),
                          ('research_plan_identity', runtime.protocol.get('config', {}).get('research_plan_identity')),
                          ('input_identity', runtime.input_identity)):
        if not isinstance(expected, str) or artifact.get(key) != expected:
            raise MonteCarloRunnerError('monte_carlo_upstream_provenance_mismatch')
    values=artifact.get('returns')
    if not isinstance(values,list) or not values or any(not isinstance(value,(int,float)) for value in values):
        raise MonteCarloRunnerError('monte_carlo_upstream_returns_invalid')
    return tuple(float(value) for value in values)


def _formal_resample(values: Sequence[float], *, seed: int, count: int) -> tuple[float, ...]:
    """Internal deterministic bootstrap; never a public resampler injection."""
    if count < 1 or not values: raise MonteCarloRunnerError('monte_carlo_resample_input_invalid')
    rng=random.Random(seed)
    return tuple(float(values[rng.randrange(len(values))]) for _ in range(count))


def run_authorized_monte_carlo(*, runtime: FutureRuntimeContext, evidence: AuthorizationEvidence,
                               upstream_evidence: Mapping[str, Any], source_git_commit: str,
                               checkpoint=None, prior_rows=()):
    """Execute frozen MC chunks with fixed seed derivation and no injected simulator.

    The capability remains locked under today's policy, so this function fails
    before inspecting upstream values in normal operation.  Its construction is
    nevertheless complete for a future separately approved MC authority.
    """
    request=build_monte_carlo_execution_request(runtime=runtime)
    runtime.authorize(evidence, Capability.MONTE_CARLO)
    # ``AuthorizationEvidence.require`` keeps this capability locked today.
    # The following path is intentionally unreachable until that trusted policy
    # is separately revised; it is still structurally bound and testable using
    # the private coordinator, never by a caller-provided resampler.
    values=_validated_upstream_returns(upstream_evidence,runtime=runtime)
    base_seed=int(runtime.protocol['artifact_identity'][:16],16)
    def execute(chunk):
        seed=base_seed + int(chunk['ordinal'])
        samples=_formal_resample(values,seed=seed,count=int(request['resamples']))
        total=1.0
        for value in samples: total *= 1.0 + value
        return {'seed':seed,'samples':list(samples),'total_return':total-1.0,'source_evidence_identity':upstream_evidence['artifact_identity'],'synthetic':False,'oos_read':False}
    return _execute_verified_chunks(runtime=runtime,source_git_commit=source_git_commit,executor=execute,checkpoint=checkpoint,prior_rows=prior_rows)
