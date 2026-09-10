"""Read-only binding from accepted N10 recovery state into future stages.

It deliberately delegates locking, state validation and finalization to the
existing N10 implementation; it never reimplements task coordination or loads
market data.
"""
from __future__ import annotations
from typing import Any, Mapping
from .artifact_store import seal
from .future_data_plane import FutureDataPlaneError, FutureRuntimeContext


class FutureN10BridgeError(RuntimeError):
    pass


def bind_completed_n10_run(*, runtime: FutureRuntimeContext, run_root, manifest: Mapping[str,Any], plan: Mapping[str,Any]) -> dict[str,Any]:
    """Return a sealed anchor only for a fully finalized N10 run.

    The future protocol config must explicitly pin the N9 manifest and N10
    final-result identity.  A partial or drifted run fails before any future
    evaluator/loader can be constructed.
    """
    runtime.validate()
    config=runtime.protocol.get('config')
    if not isinstance(config,Mapping): raise FutureN10BridgeError('future_n10_config_missing')
    expected_manifest=config.get('n9_manifest_identity')
    expected_final=config.get('n10_final_result_identity')
    if not isinstance(expected_manifest,str) or len(expected_manifest)!=64 or not isinstance(expected_final,str) or len(expected_final)!=64:
        raise FutureN10BridgeError('future_n10_identity_missing')
    if manifest.get('manifest_identity')!=expected_manifest:
        raise FutureN10BridgeError('future_n9_manifest_mismatch')
    from .recoverable_execution import final_result_identity, load_run
    state=load_run(run_root,manifest,plan)
    if any(row.get('status')!='COMPLETED' for row in state.get('tasks',{}).values()):
        raise FutureN10BridgeError('future_n10_run_not_complete')
    final=final_result_identity(run_root,manifest,plan)
    if final!=expected_final: raise FutureN10BridgeError('future_n10_final_identity_mismatch')
    binding=state.get('binding',{})
    required=('research_freeze_identity','research_plan_identity','candidate_universe_hash','boundary_identity_hash','dataset_id')
    if any(not isinstance(config.get(key),str) or not config[key] for key in required):
        raise FutureN10BridgeError('future_n10_research_identity_missing')
    if any(config[key]!=binding.get(key) for key in required):
        raise FutureN10BridgeError('future_n10_research_binding_mismatch')
    return seal({'schema_version':'quantbot-future-n10-input-anchor-v1','protocol_identity':runtime.protocol['artifact_identity'],
                 'execution_plan_identity':runtime.plan['artifact_identity'],'input_identity':runtime.input_identity,
                 'n9_manifest_identity':expected_manifest,'n10_run_id':state.get('run_id'),
                 'n10_final_result_identity':final,**{key:binding[key] for key in required},
                 'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
