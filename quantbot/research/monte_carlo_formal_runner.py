"""Formal Monte Carlo entrypoint with an intentional execution hard lock."""
from __future__ import annotations
from typing import Mapping
from .authorization import Capability, locked_evidence
from .future_data_plane import FutureRuntimeContext
from .monte_carlo_protocol import MonteCarloProtocol


class MonteCarloRunnerError(RuntimeError):
    pass


def build_monte_carlo_execution_request(*, runtime: FutureRuntimeContext) -> dict[str,object]:
    """Validate the frozen MC declaration without constructing a simulator."""
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
    """Fail closed even for a caller attempting to construct a real simulator."""
    if request.get('execution_mode')!='FORMAL_LOCKED' or request.get('oos_status')!='SEALED' or request.get('oos_authorization')!='NOT_AUTHORIZED':
        raise MonteCarloRunnerError('monte_carlo_request_invalid')
    locked_evidence(Capability.MONTE_CARLO).require()
