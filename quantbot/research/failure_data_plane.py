"""Identity-bound failure diagnostics for future non-OOS stages."""
from __future__ import annotations

from dataclasses import asdict
from typing import Mapping, Sequence

from quantbot.risk.failure_supervisor import FailureEvent, RecoveryPolicy, SupervisorState, decide
from .artifact_store import seal, validate_seal
from .future_data_plane import FutureRuntimeContext
from .authorization import AuthorizationEvidence, Capability
from .future_stage_execution import _execute_verified_chunks


class FailureDataPlaneError(RuntimeError):
    pass


def build_failure_artifact(*, runtime: FutureRuntimeContext, chunk_identity: str,
                           event: FailureEvent, state: SupervisorState = SupervisorState(),
                           policy: RecoveryPolicy = RecoveryPolicy()) -> dict:
    """Seal a failure decision without allowing it to masquerade as completion."""
    runtime.validate()
    expected={row['chunk_identity'] for row in runtime.plan['chunks']}
    if chunk_identity not in expected:
        raise FailureDataPlaneError('failure_chunk_not_declared')
    if not isinstance(event.sequence,int) or event.sequence < 0 or not event.event_id or not event.message:
        raise FailureDataPlaneError('failure_event_invalid')
    decision=decide(event,state,policy)
    return seal({
        'schema_version':'quantbot-future-failure-v1',
        'protocol_identity':runtime.protocol['artifact_identity'],
        'execution_plan_identity':runtime.plan['artifact_identity'],
        'input_identity':runtime.input_identity,'chunk_identity':chunk_identity,
        'event':asdict(event),'prior_state':asdict(state),'policy':asdict(policy),
        'decision':asdict(decision),'status':'FAILED',
        'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED',
    })


def validate_failure_artifact(artifact: Mapping[str,object], *, runtime: FutureRuntimeContext) -> bool:
    runtime.validate(); validate_seal(artifact)
    if artifact.get('schema_version')!='quantbot-future-failure-v1' or artifact.get('status')!='FAILED':
        raise FailureDataPlaneError('failure_schema_or_status_invalid')
    if artifact.get('protocol_identity')!=runtime.protocol['artifact_identity'] or artifact.get('execution_plan_identity')!=runtime.plan['artifact_identity'] or artifact.get('input_identity')!=runtime.input_identity:
        raise FailureDataPlaneError('failure_provenance_invalid')
    if artifact.get('chunk_identity') not in {row['chunk_identity'] for row in runtime.plan['chunks']}:
        raise FailureDataPlaneError('failure_chunk_invalid')
    if artifact.get('oos_status')!='SEALED' or artifact.get('oos_authorization')!='NOT_AUTHORIZED':
        raise FailureDataPlaneError('failure_oos_invalid')
    try:
        event=FailureEvent(**dict(artifact['event'])); state=SupervisorState(**dict(artifact['prior_state'])); policy=RecoveryPolicy(**dict(artifact['policy']))
    except (KeyError,TypeError,ValueError) as exc:
        raise FailureDataPlaneError('failure_payload_invalid') from exc
    if artifact.get('decision')!=asdict(decide(event,state,policy)):
        raise FailureDataPlaneError('failure_decision_mismatch')
    return True


def run_authorized_failure_diagnostics(*, runtime: FutureRuntimeContext, evidence: AuthorizationEvidence,
                                      events_by_chunk: Mapping[str, FailureEvent], source_git_commit: str,
                                      checkpoint=None, prior_rows=()):
    """Persist deterministic failure-supervisor evidence through the shared coordinator.

    This accepts failure events, not an evaluator or data loader.  A normal
    chunk records an explicit ``NO_FAILURE_EVENT`` diagnostic; a supplied event
    is sealed using the accepted failure supervisor before the chunk result is
    admitted to the common checkpoint/result chain.
    """
    if runtime.protocol.get('stage') != 'failure':
        raise FailureDataPlaneError('failure_stage_required')
    runtime.authorize(evidence, Capability.TRAIN_VALIDATION)
    declared={row['chunk_identity'] for row in runtime.plan['chunks']}
    if set(events_by_chunk) - declared:
        raise FailureDataPlaneError('failure_event_chunk_undeclared')
    def execute(chunk):
        event=events_by_chunk.get(chunk['chunk_identity'])
        if event is None:
            return {'diagnostic':'NO_FAILURE_EVENT','oos_read':False}
        artifact=build_failure_artifact(runtime=runtime,chunk_identity=chunk['chunk_identity'],event=event)
        validate_failure_artifact(artifact,runtime=runtime)
        return {'diagnostic':'FAILURE_EVENT','failure_artifact_identity':artifact['artifact_identity'],'oos_read':False}
    return _execute_verified_chunks(runtime=runtime,source_git_commit=source_git_commit,executor=execute,checkpoint=checkpoint,prior_rows=prior_rows)
