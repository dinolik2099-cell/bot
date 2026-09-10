"""Create-only finalization of a future-stage result against its N10 anchor."""
from __future__ import annotations
from typing import Any, Mapping
from .artifact_store import seal, validate_seal, write_new_json
from .future_data_plane import FutureRuntimeContext


class FutureStageFinalizationError(RuntimeError):
    pass


def finalize_future_stage(*, runtime: FutureRuntimeContext, result: Mapping[str,Any],
                          n10_anchor: Mapping[str,Any], source_git_commit: str) -> dict[str,Any]:
    """Produce one immutable final package only after complete verified inputs."""
    runtime.validate_result(result)
    validate_seal(n10_anchor)
    if n10_anchor.get('schema_version')!='quantbot-future-n10-input-anchor-v1':
        raise FutureStageFinalizationError('future_finalization_n10_anchor_schema_invalid')
    for key,expected in (('protocol_identity',runtime.protocol['artifact_identity']),
                         ('execution_plan_identity',runtime.plan['artifact_identity']),
                         ('input_identity',runtime.input_identity)):
        if n10_anchor.get(key)!=expected:
            raise FutureStageFinalizationError('future_finalization_n10_anchor_binding_invalid')
    if n10_anchor.get('oos_status')!='SEALED' or n10_anchor.get('oos_authorization')!='NOT_AUTHORIZED':
        raise FutureStageFinalizationError('future_finalization_n10_anchor_oos_invalid')
    if not isinstance(source_git_commit,str) or len(source_git_commit)!=40:
        raise FutureStageFinalizationError('future_finalization_source_invalid')
    return seal({'schema_version':'quantbot-future-stage-final-v1','stage':runtime.protocol['stage'],
                 'protocol_identity':runtime.protocol['artifact_identity'],'execution_plan_identity':runtime.plan['artifact_identity'],
                 'input_identity':runtime.input_identity,'n10_anchor_identity':n10_anchor['artifact_identity'],
                 'n10_run_id':n10_anchor.get('n10_run_id'),'n10_final_result_identity':n10_anchor.get('n10_final_result_identity'),
                 'future_result_identity':result['artifact_identity'],'source_git_commit':source_git_commit,
                 'counts':dict(result['counts']),'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})


def validate_finalized_future_stage(artifact: Mapping[str,Any], *, runtime: FutureRuntimeContext,
                                    result: Mapping[str,Any], n10_anchor: Mapping[str,Any]) -> bool:
    validate_seal(artifact); runtime.validate_result(result); validate_seal(n10_anchor)
    if artifact.get('schema_version')!='quantbot-future-stage-final-v1' or artifact.get('stage')!=runtime.protocol.get('stage'):
        raise FutureStageFinalizationError('future_finalization_schema_invalid')
    expected=finalize_future_stage(runtime=runtime,result=result,n10_anchor=n10_anchor,source_git_commit=artifact.get('source_git_commit'))
    if expected.get('artifact_identity')!=artifact.get('artifact_identity'):
        raise FutureStageFinalizationError('future_finalization_identity_mismatch')
    return True


def write_finalized_future_stage(root, artifact: Mapping[str,Any]):
    validate_seal(artifact)
    return write_new_json(root,'FUTURE_STAGE_FINAL',artifact)
