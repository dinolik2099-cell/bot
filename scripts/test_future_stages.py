from __future__ import annotations
import tempfile
from quantbot.research.artifact_store import ArtifactError, seal
from quantbot.research.future_stages import *
from quantbot.research.authorization import Capability
def blocked(fn):
 try:fn()
 except (ValueError,PermissionError,ArtifactError):return
 raise AssertionError('fail_open')
def main():
 n12=seal({'schema_version':'n12','input_n11_artifact_identity':'n'*64,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 candidates=(N12CandidateInput('a'*64,'v'*64,'t'*64,'task','m','family','BTC',{'x':1}),)
 source={'dataset_id':'d','boundary_identity_hash':'b','research_freeze_identity':'f','research_plan_identity':'p','engine_identity':'engine','cost_model_identity':'cost'}
 protocol=build_portfolio_protocol(n11_identity='n'*64,n12_artifact=n12,candidates=candidates,correlation_sha256='c'*64,source=source,policy_identity='policy');assert validate_portfolio_protocol(protocol)
 bad=seal({**{k:v for k,v in protocol.items() if k!='artifact_identity'},'oos_status':'OPEN','oos_authorization':'AUTHORIZED'});blocked(lambda:validate_portfolio_protocol(bad))
 stage=FormalStageProtocol('stress',protocol['artifact_identity'],'d','b','g'*40,{'scenarios':['BASE']}).artifact();assert validate_stage_protocol(stage,accepted_input_identity=protocol['artifact_identity'])
 assert ResumableStageState(stage['artifact_identity'],StageState.INTERRUPTED).resume().state==StageState.RUNNING
 execution=build_future_stage_execution_plan(stage,accepted_input_identity=protocol['artifact_identity'],chunk_count=3)
 assert validate_future_stage_execution_plan(execution,protocol=stage,accepted_input_identity=protocol['artifact_identity'])
 chunk_ids=tuple(row['chunk_identity'] for row in execution['chunks'])
 state=ResumableStageState(stage['artifact_identity']).resume().record(chunk_ids[0],succeeded=True).record(chunk_ids[1],succeeded=False).record(chunk_ids[2],succeeded=True)
 assert state.finish(chunk_ids).state==StageState.FAILED
 blocked(lambda:state.record(chunk_ids[0],succeeded=True))
 tampered=seal({**{key:value for key,value in execution.items() if key!='artifact_identity'},'oos_status':'OPEN'})
 blocked(lambda:validate_future_stage_execution_plan(tampered,protocol=stage,accepted_input_identity=protocol['artifact_identity']))
 bad_chunk=seal({**{key:value for key,value in execution.items() if key!='artifact_identity'},'chunks':[dict(row) for row in execution['chunks']]})
 bad_chunk['chunks'][1]['chunk_identity']='0'*64; bad_chunk=seal({key:value for key,value in bad_chunk.items() if key!='artifact_identity'})
 blocked(lambda:validate_future_stage_execution_plan(bad_chunk,protocol=stage,accepted_input_identity=protocol['artifact_identity']))
 complete=ResumableStageState(stage['artifact_identity']).resume()
 for chunk_id in chunk_ids: complete=complete.record(chunk_id,succeeded=True)
 complete=complete.finish(chunk_ids)
 rows=[{'chunk_identity':chunk_id,'status':'COMPLETED','window':'TRAIN_VALIDATION','result_identity':str(index)*64} for index,chunk_id in enumerate(chunk_ids,1)]
 result=build_future_stage_result(execution,protocol=stage,accepted_input_identity=protocol['artifact_identity'],state=complete,chunk_results=rows,source_git_commit='g'*40)
 assert validate_future_stage_result(result,plan=execution,protocol=stage,accepted_input_identity=protocol['artifact_identity'])
 with tempfile.TemporaryDirectory() as root:
  write_future_stage_result(root,result,plan=execution,protocol=stage,accepted_input_identity=protocol['artifact_identity'])
  blocked(lambda:write_future_stage_result(root,result,plan=execution,protocol=stage,accepted_input_identity=protocol['artifact_identity']))
 truncated=seal({**{key:value for key,value in result.items() if key!='artifact_identity'},'chunks':result['chunks'][:-1],'counts':{'chunks':2}})
 blocked(lambda:validate_future_stage_result(truncated,plan=execution,protocol=stage,accepted_input_identity=protocol['artifact_identity']))
 with tempfile.TemporaryDirectory() as root:
  blocked(lambda:write_future_stage_result(root,truncated,plan=execution,protocol=stage,accepted_input_identity=protocol['artifact_identity']))
 assert pre_oos_gate({'n11':'x'},required=('n11','n12'))==PreOOSStatus.RESEARCH_NOT_YET_COMPLETE
 assert pre_oos_gate({'n11':'x','n12':'y'},required=('n11','n12'))==PreOOSStatus.OOS_NOT_AUTHORIZED
 blocked(lambda:require_future_stage(Capability.OOS));blocked(lambda:require_future_stage(Capability.MONTE_CARLO));blocked(lambda:require_future_stage(Capability.LIVE))
 print('FUTURE_STAGES_SYNTHETIC_TEST_OK');print('OOS_READS=0');print('FORMAL_MC_RUNS=0')
if __name__=='__main__':main()
