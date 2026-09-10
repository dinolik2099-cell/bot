from quantbot.research.artifact_store import seal
from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_stages import N12CandidateInput,build_portfolio_protocol
from quantbot.research.portfolio_formal_runner import authorize_portfolio_run,make_portfolio_window_loader,build_shared_capital_inputs,_canonical_accounting
from quantbot.research.portfolio_formal_runner import build_canonical_signal_map
import pandas as pd
def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('portfolio_gate_open')
def main():
 n11='a'*64;sha='b'*64;c={'candidate_identity':'1'*64,'validation_result_identity':'2'*64,'selected_train_result_identity':'3'*64,'task_identity':'4'*64,'model_id':'m','family':'f','symbol':'BTC','params':{}};c2={'candidate_identity':'5'*64,'validation_result_identity':'6'*64,'selected_train_result_identity':'7'*64,'task_identity':'8'*64,'model_id':'m','family':'f','symbol':'BTC','params':{}}
 manifest=seal({'schema_version':'quantbot-non-oos-series-n12-v1','input_n11_artifact_identity':n11,'candidate_count':2,'series_count':4,'rows':[{'candidate':c},{'candidate':c2}],'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 diagnostic=seal({'schema_version':'quantbot-non-oos-homogeneity-n12-v1','input_n11_artifact_identity':n11,'candidate_count':2,'correlation_file_sha256':sha,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','selection_rule_changed':False})
 n12=seal({'schema_version':'n12','input_n11_artifact_identity':n11,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
 source={k:'x' for k in ('dataset_id','boundary_identity_hash','research_freeze_identity','research_plan_identity','engine_identity','cost_model_identity')}
 p=build_portfolio_protocol(n11_identity=n11,n12_artifact=n12,candidates=(N12CandidateInput('1'*64,'2'*64,'3'*64,'4'*64,'m','f','BTC',{}),N12CandidateInput('5'*64,'6'*64,'7'*64,'8'*64,'m','f','BTC',{})),correlation_sha256=sha,source=source,policy_identity='policy')
 e=AuthorizationEvidence(Capability.TRAIN_VALIDATION)
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=2,correlation_sha256=sha,evidence=e))
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity='c'*64,candidate_count=2,correlation_sha256=sha,evidence=e))
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=2,correlation_sha256='d'*64,evidence=e))
 blocked(lambda:authorize_portfolio_run(protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=2,correlation_sha256=sha,evidence=AuthorizationEvidence(Capability.OOS)))
 blocked(lambda:make_portfolio_window_loader(n8_context=None,raw_root='must-not-open',protocol=p,diagnostic=diagnostic,manifest=manifest,n11_identity=n11,candidate_count=2,correlation_sha256=sha,evidence=e))
 index=pd.date_range('2025-01-01',periods=3,freq='h',tz='UTC');frame=pd.DataFrame({'open':[1,2,3],'high':[2,3,4],'low':[.5,1,2],'close':[1,2,3],'volume':[1,1,1]},index=index)
 def strategy(df,**_): return pd.DataFrame({'signal':[0,1,0],'stop':[None,1.0,None],'target':[None,3.0,None]},index=df.index)
 signals=build_canonical_signal_map(frame=frame,strategy=strategy,params={},model_id='m',symbol='BTC',task_identity='4'*64)
 assert list(signals[('m','BTC')])==[index[2]] and signals[('m','BTC')][index[2]]['tag']=='4'*64
 prepared=build_shared_capital_inputs(frames_by_symbol={'BTC':frame},protocol=p,manifest=manifest,strategy_resolver=lambda _:strategy)
 assert prepared['candidate_count']==2 and prepared['recipe_keys']==[('1'*64,'BTC'),('5'*64,'BTC')]
 assert prepared['sleeve_provenance']['1'*64]['model_id']=='m'
 bad_manifest=dict(manifest);bad_manifest['rows']=[{'candidate':dict(c,params={'forged':1})},{'candidate':c2}]
 blocked(lambda:build_shared_capital_inputs(frames_by_symbol={'BTC':frame},protocol=p,manifest=bad_manifest,strategy_resolver=lambda _:strategy))
 from quantbot.portfolio.shared_capital import Trade
 trade=Trade('BTC','buy','a','b',1,1,1,0,0,0,0,'x','tag',['s','BTC'])
 assert _canonical_accounting({'curve':[('t',1.0)],'trades':[trade]})['trades'][0]['symbol']=='BTC'
 print('PORTFOLIO_CANDIDATE_SLEEVE_BINDING_SYNTHETIC_TEST_OK')
 print('PORTFOLIO_FORMAL_RUNNER_GATE_SYNTHETIC_TEST_OK');print('PROTECTED_READS=0');print('OOS_READS=0');print('SHARED_CAPITAL_CALLS=0')
if __name__=='__main__':main()
