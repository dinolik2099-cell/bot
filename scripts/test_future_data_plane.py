from quantbot.research.artifact_store import seal
from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
def main():
 input_id='a'*64;p=FormalStageProtocol('stress',input_id,'d','b','g'*40,{}).artifact();plan=build_future_stage_execution_plan(p,accepted_input_identity=input_id,chunk_count=2);ctx=FutureRuntimeContext(p,plan,input_id)
 try:ctx.authorize(AuthorizationEvidence(Capability.TRAIN_VALIDATION),Capability.TRAIN_VALIDATION)
 except PermissionError:pass
 else:raise AssertionError('unauthorized_data_plane_open')
 try:ctx.authorize(AuthorizationEvidence(Capability.OOS),Capability.TRAIN_VALIDATION)
 except Exception:pass
 else:raise AssertionError('wrong_capability_open')
 rows=[{'chunk_identity':row['chunk_identity'],'status':'COMPLETED','window':'TRAIN_VALIDATION','protocol_identity':p['artifact_identity'],'execution_plan_identity':plan['artifact_identity'],'input_identity':input_id,'result_identity':str(index+1)*64,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'} for index,row in enumerate(plan['chunks'])]
 result=ctx.result(rows,'g'*40);assert ctx.validate_result(result)
 for mutate in (lambda r:r['rows'].pop(),lambda r:r['rows'][0].__setitem__('oos_authorization','AUTHORIZED'),lambda r:r['rows'][0].__setitem__('status','PARTIAL')):
  bad=dict(result);bad['rows']=[dict(row) for row in result['rows']];mutate(bad)
  try:ctx.validate_result(bad)
  except Exception:pass
  else:raise AssertionError('future_result_tamper_open')
 print('FUTURE_DATA_PLANE_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0')
if __name__=='__main__':main()
