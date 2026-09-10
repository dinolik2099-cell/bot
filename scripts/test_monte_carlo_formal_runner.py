from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
from quantbot.research.monte_carlo_formal_runner import build_monte_carlo_execution_request,require_monte_carlo_execution_authority
def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('monte_carlo_formal_path_open')
def main():
 input_id='a'*64;config={'protocol':{'resamples':100},'execution_mode':'FORMAL_LOCKED'};protocol=FormalStageProtocol('monte_carlo',input_id,'d','b','c'*40,config).artifact();plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=1);runtime=FutureRuntimeContext(protocol,plan,input_id);request=build_monte_carlo_execution_request(runtime=runtime);blocked(lambda:require_monte_carlo_execution_authority(request));blocked(lambda:build_monte_carlo_execution_request(runtime=FutureRuntimeContext(FormalStageProtocol('monte_carlo',input_id,'d','b','c'*40,{'protocol':{'resamples':100},'execution_mode':'OPEN'}).artifact(),plan,input_id)))
 print('MONTE_CARLO_FORMAL_RUNNER_SYNTHETIC_TEST_OK');print('FORMAL_MC_RUNS=0');print('OOS_READS=0')
if __name__=='__main__':main()
