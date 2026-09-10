from quantbot.research.failure_data_plane import build_failure_artifact,validate_failure_artifact
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
from quantbot.risk.failure_supervisor import FailureEvent,FailureCategory,Severity
def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('failure_data_plane_open')
def main():
 input_id='a'*64;protocol=FormalStageProtocol('failure',input_id,'d','b','c'*40,{}).artifact();plan=build_future_stage_execution_plan(protocol,accepted_input_identity=input_id,chunk_count=1);runtime=FutureRuntimeContext(protocol,plan,input_id);event=FailureEvent('e',FailureCategory.DATA,Severity.RETRYABLE,'missing bar',0)
 artifact=build_failure_artifact(runtime=runtime,chunk_identity=plan['chunks'][0]['chunk_identity'],event=event);assert validate_failure_artifact(artifact,runtime=runtime);assert artifact['decision']['terminal']
 bad=dict(artifact);bad['status']='COMPLETED';blocked(lambda:validate_failure_artifact(bad,runtime=runtime))
 bad=dict(artifact);bad['decision']=dict(artifact['decision']);bad['decision']['action']='RETRY';blocked(lambda:validate_failure_artifact(bad,runtime=runtime))
 print('FAILURE_DATA_PLANE_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0');print('FORMAL_FAILURE_RUNS=0')
if __name__=='__main__':main()
