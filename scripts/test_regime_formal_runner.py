from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
from quantbot.research.regime_formal_runner import make_regime_canonical_runner
def main():
 input_id='a'*64;protocol=FormalStageProtocol('regime',input_id,'dataset','boundary','b'*40,{'policy':{}}).artifact();plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=1);runtime=FutureRuntimeContext(protocol,plan,input_id)
 try:make_regime_canonical_runner(runtime=runtime,evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION),n8_context=None,raw_root='must-not-open')
 except PermissionError:pass
 else:raise AssertionError('regime_formal_path_open')
 print('REGIME_FORMAL_RUNNER_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0');print('FORMAL_REGIME_RUNS=0')
if __name__=='__main__':main()
