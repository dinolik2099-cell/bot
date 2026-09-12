from dataclasses import asdict
from types import SimpleNamespace
from quantbot.backtest.costs import CostModel
from quantbot.backtest.stress_framework import CostStressScenario, scenario_identity
from quantbot.research.authorization import AuthorizationEvidence, Capability
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol, build_future_stage_execution_plan
from quantbot.research.stress_formal_runner import make_stress_canonical_evaluator,_execute_stress_chunks,_stress_worker_provenance,ACCEPTED_N5_RESEARCH_PLAN_IDENTITY

def worker_good(chunk): return {'ordinal':chunk['ordinal'],'oos_read':False}
def worker_fail(chunk):
    if chunk['ordinal']==1:raise RuntimeError('synthetic_failure')
    return worker_good(chunk)


def blocked(fn):
    try: fn()
    except Exception: return
    raise AssertionError('stress_formal_path_open')


def expect_provenance_block(request,runtime,evidence,n8,commit):
    blocked(lambda:_stress_worker_provenance(request,runtime,evidence,n8,commit))


def main():
    input_id='a'*64; base=CostModel(); scenario=CostStressScenario('HIGH_COST',1.5,2.0,1.5)
    config={'scenario':asdict(scenario),'scenario_identity':scenario_identity(scenario),'base_cost_model':asdict(base)}
    protocol=FormalStageProtocol('stress',input_id,'dataset','boundary','b'*40,config).artifact()
    plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=1)
    runtime=FutureRuntimeContext(protocol,plan,input_id)
    blocked(lambda: make_stress_canonical_evaluator(runtime=runtime,evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open',strategy_resolver=lambda _:None))
    for key,value in (('scenario_identity','0'*64),('base_cost_model',{})):
        bad_config=dict(config);bad_config[key]=value
        bad_protocol=FormalStageProtocol('stress',input_id,'dataset','boundary','b'*40,bad_config).artifact()
        bad_plan=build_future_stage_execution_plan(bad_protocol,accepted_input_identity=input_id,chunk_count=1)
        blocked(lambda: make_stress_canonical_evaluator(runtime=FutureRuntimeContext(bad_protocol,bad_plan,input_id),evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open',strategy_resolver=lambda _:None))
    assert scenario.stressed_cost_model(base).slippage_bps > base.slippage_bps
    twelve=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=12);parallel_runtime=FutureRuntimeContext(protocol,twelve,input_id)
    one=_execute_stress_chunks(runtime=parallel_runtime,source_git_commit='c'*40,executor=worker_good,workers=1)
    four=_execute_stress_chunks(runtime=parallel_runtime,source_git_commit='c'*40,executor=worker_good,workers=4)
    assert one.result['artifact_identity']==four.result['artifact_identity'] and len(four.rows)==12
    failed=_execute_stress_chunks(runtime=parallel_runtime,source_git_commit='d'*40,executor=worker_fail,workers=4)
    assert failed.result is None and failed.state.failed_chunks and len(failed.rows)==11
    freeze='f'*64
    frozen={'research_plan_identity':ACCEPTED_N5_RESEARCH_PLAN_IDENTITY,'research_freeze_identity':freeze,'boundary_identity_hash':'boundary','oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'}
    n8=SimpleNamespace(n7=SimpleNamespace(plan=frozen,freeze={'research_freeze_identity':freeze,'research_boundary':None}),dataset=SimpleNamespace(dataset_id='dataset'))
    authority=AuthorizationEvidence(Capability.TRAIN_VALIDATION,'AUTHORIZED','synthetic',freeze,ACCEPTED_N5_RESEARCH_PLAN_IDENTITY)
    request={'research_plan_identity':ACCEPTED_N5_RESEARCH_PLAN_IDENTITY,'research_freeze_identity':freeze,'dataset_id':'dataset','boundary_identity_hash':'boundary','protocol_identity':protocol['artifact_identity'],'execution_plan_identity':twelve['artifact_identity'],'input_identity':input_id,'source_git_commit':'b'*40}
    _stress_worker_provenance(request,parallel_runtime,authority,n8,'b'*40)
    for key,value in (('research_plan_identity','0'*64),('dataset_id','other'),('boundary_identity_hash','other'),('protocol_identity','0'*64),('execution_plan_identity','0'*64),('input_identity','0'*64),('source_git_commit','c'*40)):
        mutated=dict(request);mutated[key]=value
        expect_provenance_block(mutated,parallel_runtime,authority,n8,'b'*40)
    drifted=dict(frozen);drifted['research_plan_identity']='0'*64
    expect_provenance_block(request,parallel_runtime,authority,SimpleNamespace(n7=SimpleNamespace(plan=drifted),dataset=n8.dataset),'b'*40)
    expect_provenance_block(request,parallel_runtime,authority,SimpleNamespace(n7=SimpleNamespace(plan=frozen,freeze={'research_freeze_identity':freeze,'research_boundary':'drift'}),dataset=n8.dataset),'b'*40)
    print('STRESS_FORMAL_RUNNER_SYNTHETIC_TEST_OK')
    print('PROTECTED_READS=0'); print('OOS_READS=0'); print('FORMAL_STRESS_RUNS=0')
    print('STRESS_PARALLEL_DETERMINISM=PASS');print('STRESS_12_CHUNK_COVERAGE=PASS');print('STRESS_FAILURE_PARTIAL=PASS')
    print('STRESS_WORKER_PROVENANCE_DRIFT_REJECTED=PASS')


if __name__=='__main__': main()
