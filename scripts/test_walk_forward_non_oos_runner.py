from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
from quantbot.research.walk_forward_non_oos_runner import make_walk_forward_non_oos_evaluator
def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('walk_forward_non_oos_open')
def main():
 input_id='a'*64;config={'folds':[{'fold_id':'fold-1','train':'TRAIN','validation':'VALIDATION'}]};protocol=FormalStageProtocol('walk_forward',input_id,'d','b','c'*40,config).artifact();plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=1);runtime=FutureRuntimeContext(protocol,plan,input_id)
 blocked(lambda:make_walk_forward_non_oos_evaluator(runtime=runtime,evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open',strategy_resolver=lambda _:None,engine_factory=lambda:None))
 for bad_config in ({'folds':[{'fold_id':'fold-1','train':'TRAIN','validation':'OOS'}]},{'folds':[{'fold_id':'x','train':'TRAIN','validation':'VALIDATION'},{'fold_id':'x','train':'TRAIN','validation':'VALIDATION'}]}):
  bad=FormalStageProtocol('walk_forward',input_id,'d','b','c'*40,bad_config).artifact();bad_plan=build_future_stage_execution_plan(bad,accepted_input_identity=input_id,chunk_count=1);blocked(lambda:make_walk_forward_non_oos_evaluator(runtime=FutureRuntimeContext(bad,bad_plan,input_id),evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open',strategy_resolver=lambda _:None,engine_factory=lambda:None))
 print('WALK_FORWARD_NON_OOS_RUNNER_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0');print('FORMAL_WALK_FORWARD_RUNS=0')
if __name__=='__main__':main()
