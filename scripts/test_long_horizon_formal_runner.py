from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
from quantbot.research.long_horizon_formal_runner import make_long_horizon_canonical_evaluator
def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('long_horizon_formal_path_open')
def main():
 input_id='a'*64;config={'protocol':{},'windows':(180,200,240)};protocol=FormalStageProtocol('long_horizon',input_id,'d','b','c'*40,config).artifact();plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=1);runtime=FutureRuntimeContext(protocol,plan,input_id)
 blocked(lambda:make_long_horizon_canonical_evaluator(runtime=runtime,evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open',strategy_resolver=lambda _:None,engine_factory=lambda:None))
 bad=FormalStageProtocol('long_horizon',input_id,'d','b','c'*40,{'protocol':{},'windows':(180,200)}).artifact();bad_plan=build_future_stage_execution_plan(bad,accepted_input_identity=input_id,chunk_count=1);blocked(lambda:make_long_horizon_canonical_evaluator(runtime=FutureRuntimeContext(bad,bad_plan,input_id),evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open',strategy_resolver=lambda _:None,engine_factory=lambda:None))
 print('LONG_HORIZON_FORMAL_RUNNER_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0');print('FORMAL_LONG_HORIZON_RUNS=0')
if __name__=='__main__':main()
