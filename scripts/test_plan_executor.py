from pathlib import Path
import sys,json,tempfile,math
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.plan_executor import authorize_window,rank_train,PlanExecutionError,execute_synthetic_cell,load_verified_plan,load_task_frame,execute_verified_plan,execution_audit,validate_execution_outputs,preflight_summary,validate_metrics,make_canonical_evaluator
from quantbot.research.model_registry import ModelSpec,RegisteredModel
def main():
 try:authorize_window({},'OOS')
 except PlanExecutionError:pass
 else:raise AssertionError('OOS must fail')
 rows=[{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':2}},{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':1}}]
 assert rank_train(rows)[0]['params']['a']==1
 class E: model_id='m';parameter_grid={'x':(1,2,3)}
 def ev(window,entry,task,params): return {'total_return':float(next(iter(params.values()))),'max_drawdown':.1,'profit_factor':1.0,'trades':1}
 out=execute_synthetic_cell(E(),{'task_identity':'t','model_id':'m','symbol':'S'},ev,top_k=2)
 assert len(out['train'])==3 and len(out['validation'])==2 and all(not x['oos_authorized'] for x in out['validation'])
 assert validate_metrics({'total_return':0.0,'max_drawdown':0.0,'profit_factor':math.inf,'trades':0})['trades']==0
 from quantbot.backtest.engine_v2 import BacktestEngine
 from quantbot.backtest.costs import CostModel
 import pandas as pd
 index=pd.date_range('2026-01-01',periods=3,freq='h',tz='UTC');frame=pd.DataFrame({'open':[1.,1.,1.],'high':[1.,1.,1.],'low':[1.,1.,1.],'close':[1.,1.,1.],'volume':[1.,1.,1.]},index=index)
 def flat(df,**kwargs):return pd.DataFrame({'signal':0,'stop':float('nan'),'target':float('nan')},index=df.index)
 canonical=make_canonical_evaluator(lambda **kwargs:frame,lambda model_id:flat,lambda:BacktestEngine(initial_equity=1000,cost_model=CostModel()))
 assert canonical('TRAIN',E(),{'symbol':'S','task_identity':'t'},{'x':1})['trades']==0
 try:make_canonical_evaluator(lambda **kwargs:frame,lambda _:flat,lambda:object())('TRAIN',E(),{'symbol':'S','task_identity':'t'},{})
 except PlanExecutionError:pass
 else:raise AssertionError('canonical engine guard')
 # No data interface exists in load_verified_plan; a bad plan must fail during metadata preflight.
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'plan.json';bad=json.loads((ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json').read_text());bad['research_plan_identity']='x'*64;p.write_text(json.dumps(bad))
  lock=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text())
  try:load_verified_plan(p,ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json',lock)
  except Exception:pass
  else:raise AssertionError('tampered plan must fail before data')
  from quantbot.research.model_registry import list_models
  before=list_models();_,verified_entries=load_verified_plan(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json',ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json',lock);assert list_models()==before
  summary=preflight_summary(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json',ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json',lock);assert summary['models']==36 and summary['tasks']==216 and summary['oos_authorization']=='NOT_AUTHORIZED'
 plan=json.loads((ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json').read_text());freeze=json.loads((ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json').read_text());calls=[]
 def loader(**kwargs):calls.append(kwargs);return 'synthetic-frame'
 task=plan['tasks'][0];assert load_task_frame(plan,task['task_identity'],'TRAIN',loader)=='synthetic-frame' and len(calls)==1
 for identity,window in (('bad','TRAIN'),(task['task_identity'],'OOS')):
  try:load_task_frame(plan,identity,window,loader)
  except PlanExecutionError:pass
  else:raise AssertionError('pre-read guard')
 assert len(calls)==1
 bad_plan=json.loads(json.dumps(plan));bad_plan['protocol_scope_hash']='x'*64
 try:load_task_frame(bad_plan,task['task_identity'],'TRAIN',loader)
 except PlanExecutionError:pass
 else:raise AssertionError('protocol guard')
 assert len(calls)==1
 bad_plan=json.loads(json.dumps(plan));bad_plan['tasks'][0]['task_identity']='z'*64
 try:load_task_frame(bad_plan,'z'*64,'TRAIN',loader)
 except PlanExecutionError:pass
 else:raise AssertionError('task guard')
 assert len(calls)==1
 # Full-plan dispatcher is deterministic and preserves plan/freeze provenance.
 from quantbot.research.candidate_universe import build_candidate_universe
 entries=verified_entries
 outputs=execute_verified_plan(plan,entries,ev,freeze)
 assert [x['task_identity'] for x in outputs]==sorted(x['task_identity'] for x in outputs) and all(x['research_plan_identity']==plan['research_plan_identity'] for x in outputs)
 audit=execution_audit(plan,outputs,entries);assert audit['tasks_completed']==len(plan['tasks']) and audit['oos_authorization']=='NOT_AUTHORIZED'
 assert validate_execution_outputs(plan,outputs,entries)
 # N6 output tamper matrix: each mutation must be rejected without any data access.
 def clone(): return json.loads(json.dumps(outputs))
 def rejected(mutator):
  candidate=clone();mutator(candidate)
  try:validate_execution_outputs(plan,candidate,entries)
  except PlanExecutionError:return
  raise AssertionError('tampered execution output unexpectedly accepted')
 rejected(lambda rows:rows[0].__setitem__('parameter_grid_hash','x'*64))
 rejected(lambda rows:rows[0]['train'].pop())
 rejected(lambda rows:rows[0]['validation'].pop())
 rejected(lambda rows:rows[0].__setitem__('status','PENDING'))
 def failed_with_results(rows):rows[0]['status']='FAILED';rows[0]['error_type']='Synthetic';rows[0]['error_message']='failure'
 rejected(failed_with_results)
 rejected(lambda rows:rows[0]['train'][1].__setitem__('params',dict(rows[0]['train'][0]['params'])))
 def extra_train(rows):rows[0]['train'].append(dict(rows[0]['train'][0]))
 rejected(extra_train)
 rejected(lambda rows:rows[0]['train'][0].__setitem__('params',{'not_frozen':1}))
 def non_top_validation(rows):
  selected={json.dumps(x['params'],sort_keys=True) for x in rows[0]['validation']}
  source=next(x for x in rows[0]['train'] if json.dumps(x['params'],sort_keys=True) not in selected)
  rows[0]['validation'][0]['params']=dict(source['params'])
 rejected(non_top_validation)
 rejected(lambda rows:rows[0]['validation'][1].__setitem__('params',dict(rows[0]['validation'][0]['params'])))
 rejected(lambda rows:rows[0].__setitem__('error_message','unexpected'))
 def failed_without_type(rows):
  row=rows[0];row['status']='FAILED';row.pop('train');row.pop('validation');row['error_message']='failure';row.pop('error_type',None)
 rejected(failed_without_type)
 def failed_with_train(rows):
  row=rows[0];row['status']='FAILED';row['error_type']='Synthetic';row['error_message']='failure';row.pop('validation')
 rejected(failed_with_train)
 def failed_with_validation(rows):
  row=rows[0];row['status']='FAILED';row['error_type']='Synthetic';row['error_message']='failure';row.pop('train')
 rejected(failed_with_validation)
 def audit_rejects(rows):
  rows[0]['status']='UNKNOWN';execution_audit(plan,rows,entries)
 try:audit_rejects(clone())
 except PlanExecutionError:pass
 else:raise AssertionError('audit must reject invalid outputs')
 def broken(*args):raise ValueError('synthetic evaluator failure')
 failed=execute_verified_plan(plan,entries,broken,freeze)
 assert all(x['status']=='FAILED' and x['research_freeze_identity']==plan['research_freeze_identity'] for x in failed)
 def invalid(*args):return {'total_return':1}
 assert execute_verified_plan(plan,entries,invalid,freeze)[0]['status']=='FAILED'
 tampered=json.loads(json.dumps(plan));tampered['boundary']['actual_end']='2099-01-01T00:00:00Z';tampered['boundary_identity_hash']=__import__('quantbot.research.research_plan',fromlist=['identity_payload'])._hash(tampered['boundary']);tampered['research_plan_identity']=__import__('quantbot.research.research_plan',fromlist=['identity_payload'])._hash(__import__('quantbot.research.research_plan',fromlist=['identity_payload']).identity_payload(tampered));before_calls=len(calls)
 try:execute_verified_plan(tampered,entries,ev,freeze)
 except ValueError:pass
 else:raise AssertionError('dispatcher must validate freeze anchor before evaluator')
 assert len(calls)==before_calls
 print('PLAN_EXECUTOR_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
