from __future__ import annotations
from quantbot.research.artifact_store import seal
from quantbot.research.future_stages import *
from quantbot.research.authorization import Capability
def blocked(fn):
 try:fn()
 except (ValueError,PermissionError):return
 raise AssertionError('fail_open')
def main():
 n12=seal({'schema_version':'n12','input_n11_artifact_identity':'n'*64,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 candidates=(N12CandidateInput('a'*64,'v'*64,'t'*64,'task','m','family','BTC',{'x':1}),)
 source={'dataset_id':'d','boundary_identity_hash':'b','research_freeze_identity':'f','research_plan_identity':'p','engine_identity':'engine','cost_model_identity':'cost'}
 protocol=build_portfolio_protocol(n11_identity='n'*64,n12_artifact=n12,candidates=candidates,correlation_sha256='c'*64,source=source,policy_identity='policy');assert validate_portfolio_protocol(protocol)
 bad=seal({**{k:v for k,v in protocol.items() if k!='artifact_identity'},'oos_status':'OPEN','oos_authorization':'AUTHORIZED'});blocked(lambda:validate_portfolio_protocol(bad))
 stage=FormalStageProtocol('stress',protocol['artifact_identity'],'d','b','g'*40,{'scenarios':['BASE']}).artifact();assert validate_stage_protocol(stage,accepted_input_identity=protocol['artifact_identity'])
 assert ResumableStageState(stage['artifact_identity'],StageState.INTERRUPTED).resume().state==StageState.RUNNING
 assert pre_oos_gate({'n11':'x'},required=('n11','n12'))==PreOOSStatus.RESEARCH_NOT_YET_COMPLETE
 assert pre_oos_gate({'n11':'x','n12':'y'},required=('n11','n12'))==PreOOSStatus.OOS_NOT_AUTHORIZED
 blocked(lambda:require_future_stage(Capability.OOS));blocked(lambda:require_future_stage(Capability.MONTE_CARLO));blocked(lambda:require_future_stage(Capability.LIVE))
 print('FUTURE_STAGES_SYNTHETIC_TEST_OK');print('OOS_READS=0');print('FORMAL_MC_RUNS=0')
if __name__=='__main__':main()
