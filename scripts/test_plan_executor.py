from pathlib import Path
import sys,json,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.plan_executor import authorize_window,rank_train,PlanExecutionError,execute_synthetic_cell,load_verified_plan,load_task_frame,execute_verified_plan,execution_audit
from quantbot.research.model_registry import ModelSpec,RegisteredModel
def main():
 try:authorize_window({},'OOS')
 except PlanExecutionError:pass
 else:raise AssertionError('OOS must fail')
 rows=[{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':2}},{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':1}}]
 assert rank_train(rows)[0]['params']['a']==1
 class E: parameter_grid={'x':(1,2,3)}
 def ev(window,entry,task,params): return {'total_return':float(next(iter(params.values()))),'max_drawdown':.1,'profit_factor':1.0,'trades':1}
 out=execute_synthetic_cell(E(),{'task_identity':'t','model_id':'m','symbol':'S'},ev,top_k=2)
 assert len(out['train'])==3 and len(out['validation'])==2 and all(not x['oos_authorized'] for x in out['validation'])
 # No data interface exists in load_verified_plan; a bad plan must fail during metadata preflight.
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'plan.json';bad=json.loads((ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json').read_text());bad['research_plan_identity']='x'*64;p.write_text(json.dumps(bad))
  lock=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text())
  try:load_verified_plan(p,ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json',lock)
  except Exception:pass
  else:raise AssertionError('tampered plan must fail before data')
  from quantbot.research.model_registry import list_models
  before=list_models();_,verified_entries=load_verified_plan(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json',ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json',lock);assert list_models()==before
 plan=json.loads((ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json').read_text());calls=[]
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
 subset=dict(plan);subset['tasks']=plan['tasks'][:2]
 outputs=execute_verified_plan(subset,entries,ev)
 assert [x['task_identity'] for x in outputs]==sorted(x['task_identity'] for x in outputs) and all(x['research_plan_identity']==plan['research_plan_identity'] for x in outputs)
 audit=execution_audit(plan,outputs);assert audit['tasks_completed']==2 and audit['oos_authorization']=='NOT_AUTHORIZED'
 def broken(*args):raise ValueError('synthetic evaluator failure')
 failed=execute_verified_plan(subset,entries,broken)
 assert all(x['status']=='FAILED' and x['research_freeze_identity']==plan['research_freeze_identity'] for x in failed)
 print('PLAN_EXECUTOR_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
