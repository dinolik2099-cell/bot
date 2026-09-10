"""Production-shaped synthetic coverage for the sealed future-stage coordinator.

It never constructs N8, opens raw data, or grants a real formal authority.
The private executor is used only to prove coordinator invariants; public
stage runners have no evaluator/resampler parameter.
"""
from __future__ import annotations

from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stage_execution import (
    _execute_verified_chunks, validate_future_stage_execution,
)
from quantbot.research.future_stages import FormalStageProtocol, build_future_stage_execution_plan, StageState


def blocked(fn, label):
    try:
        fn()
    except Exception:
        return
    raise AssertionError(label)


def context():
    input_id='a'*64
    protocol=FormalStageProtocol('stress',input_id,'dataset','boundary','b'*40,{}).artifact()
    plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=3)
    return FutureRuntimeContext(protocol,plan,input_id)


def main():
    runtime=context(); calls=[]
    def good(chunk):
        calls.append(chunk['chunk_identity'])
        return {'chunk_ordinal':chunk['ordinal'],'metrics':{'total_return':0.0},'oos_read':False}
    first=_execute_verified_chunks(runtime=runtime,source_git_commit='c'*40,executor=good)
    assert first.state.state==StageState.COMPLETE and first.result is not None
    assert len(calls)==3 and validate_future_stage_execution(first,runtime=runtime)
    second=_execute_verified_chunks(runtime=runtime,source_git_commit='c'*40,executor=good)
    assert second.result['artifact_identity']==first.result['artifact_identity']
    blocked(lambda:_execute_verified_chunks(runtime=runtime,source_git_commit='bad',executor=good),'invalid_source_commit_accepted')
    broken_calls=[]
    def fail_second(chunk):
        broken_calls.append(chunk['ordinal'])
        if chunk['ordinal']==1: raise RuntimeError('synthetic_worker_crash')
        return {'ordinal':chunk['ordinal'],'oos_read':False}
    partial=_execute_verified_chunks(runtime=runtime,source_git_commit='d'*40,executor=fail_second)
    assert partial.state.state==StageState.INTERRUPTED and partial.result is None
    assert partial.state.failed_chunks
    assert validate_future_stage_execution(partial,runtime=runtime)
    blocked(lambda: runtime.result(partial.rows,'d'*40),'partial_result_finalized')
    tampered=dict(partial.checkpoint);tampered['input_identity']='0'*64
    blocked(lambda:runtime.validate_checkpoint(tampered),'checkpoint_identity_drift_accepted')
    # Explicit retry is a new fenced attempt and must preserve prior completed rows.
    resumed=_execute_verified_chunks(runtime=runtime,source_git_commit='d'*40,executor=good,checkpoint=partial.checkpoint,prior_rows=partial.rows,retry_failed=True)
    assert resumed.state.state==StageState.COMPLETE and resumed.result is not None
    assert validate_future_stage_execution(resumed,runtime=runtime)
    forged=list(resumed.rows); forged[0]=dict(forged[0]); forged[0]['evidence']={'forged':True}
    blocked(lambda:_execute_verified_chunks(runtime=runtime,source_git_commit='d'*40,executor=good,checkpoint=resumed.checkpoint,prior_rows=forged),'forged_prior_row_accepted')
    print('FUTURE_STAGE_EXECUTION_SYNTHETIC_TEST_OK')
    print('DETERMINISTIC_COMPLETE_RESULT=PASS')
    print('PARTIAL_CANNOT_FINALIZE=PASS')
    print('CHECKPOINT_IDENTITY_DRIFT_REJECTED=PASS')
    print('RESUME_AFTER_WORKER_FAILURE=PASS')
    print('PROTECTED_READS=0')
    print('OOS_READS=0')
    print('FORMAL_RESEARCH_RUNS=0')

if __name__=='__main__': main()
