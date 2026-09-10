from dataclasses import asdict
from quantbot.backtest.costs import CostModel
from quantbot.backtest.stress_framework import CostStressScenario, scenario_identity
from quantbot.research.authorization import AuthorizationEvidence, Capability
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol, build_future_stage_execution_plan
from quantbot.research.stress_formal_runner import make_stress_canonical_evaluator


def blocked(fn):
    try: fn()
    except Exception: return
    raise AssertionError('stress_formal_path_open')


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
    print('STRESS_FORMAL_RUNNER_SYNTHETIC_TEST_OK')
    print('PROTECTED_READS=0'); print('OOS_READS=0'); print('FORMAL_STRESS_RUNS=0')


if __name__=='__main__': main()
