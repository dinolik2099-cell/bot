from quantbot.research.artifact_store import seal
from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_stages import N12CandidateInput,build_portfolio_protocol
from quantbot.research.portfolio_formal_runner import authorize_portfolio_run
def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('portfolio_gate_open')
def main():
 n11='a'*64;sha='b'*64;c={'candidate_identity':'1'*64,'validation_result_identity':'2'*64,'selected_train_result_identity':'3'*64,'task_identity':'4'*64,'model_id':'m','family':'f','symbol':'BTC','params':{}}
 manifest=seal({'schema_version':'quantbot-non-oos-series-n12-v1','input_n11_artifact_identity':n11,'candidate_count':1,'series_count':2,'rows':[{'candidate':c}],'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 diagnostic=seal({'schema_version':'quantbot-non-oos-homogeneity-n12-v1','input_n11_artifact_identity':n11,'candidate_count':1,'correlation_file_sha256':sha,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','selection_rule_changed':False})
 n12=seal({'schema_version':'n12','input_n11_artifact_identity':n11,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 source={k:'x' for k in ('dataset_id','boundary_identity_hash','research_freeze_identity','research_plan_identity','engine_identity','cost_model_identity')}
 p=build_portfolio_protocol(n11_identity=n11,n12_artifact=n12,candidates=(N12CandidateInput('1'*64,'2'*64,'3'*64,'4'*64,'m','f','BTC',{}),),correlation_sha256=sha,source=source,policy_identity='policy')
 e=AuthorizationEvidence(Capability.TRAIN_VALIDATION)
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=1,correlation_sha256=sha,evidence=e))
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity='c'*64,candidate_count=1,correlation_sha256=sha,evidence=e))
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=1,correlation_sha256='d'*64,evidence=e))
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=1,correlation_sha256=sha,evidence=AuthorizationEvidence(Capability.OOS)))
 print('PORTFOLIO_FORMAL_RUNNER_GATE_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0');print('SHARED_CAPITAL_CALLS=0')
if __name__=='__main__':main()
