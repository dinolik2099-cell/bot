"""Synthetic-only N10 state/recovery adversarial contract tests."""
from pathlib import Path
import json,sys,tempfile,subprocess,copy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest
from quantbot.research.plan_executor import rank_train
from quantbot.research.recoverable_execution import (
 RecoverableExecutionError,initialize_run,load_run,unfinished_task_ids,claim_task,
 task_result_payload,complete_task,fail_task,final_result_identity,_task_path,_write_new,
 _run_lock,validate_task_artifact,_hash
)
LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'
def clone(v): return copy.deepcopy(v)
def rejected(fn, contains=None):
 try: fn()
 except RecoverableExecutionError as exc:
  if contains is not None: assert contains in str(exc),(contains,str(exc))
  return str(exc)
 raise AssertionError('unexpectedly accepted')
def clean_repo(path):
 subprocess.check_call(['git','init','-q',str(path)]);subprocess.check_call(['git','-C',str(path),'config','user.email','n10@example.invalid']);subprocess.check_call(['git','-C',str(path),'config','user.name','N10']);(path/'README').write_text('n10');subprocess.check_call(['git','-C',str(path),'add','README']);subprocess.check_call(['git','-C',str(path),'commit','-q','-m','n10']);return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
def context(td,n7,n8,name='N10_RESULT.json'):
 repo=Path(td)/'repo';repo.mkdir();commit=clean_repo(repo);manifest=build_manifest(n7,n8,source_git_commit=commit,worker_config={'workers':2},output_destination=f'data/reports/formal_runs/{name}',created_at='synthetic');authority={'n7':n7,'n8':n8,'repo_root':repo,'requested_windows':{'TRAIN':manifest['train_window'],'VALIDATION':manifest['validation_window']},'output_path':manifest['output']['destination'],'requested_workers':2};return repo,manifest,authority
def result_rows(state,task):
 grid=state['binding']['parameter_grids'][task['model_id']];keys=sorted(grid)
 from itertools import product
 rows=[]
 for i,vals in enumerate(product(*(grid[k] for k in keys))):
  params=dict(zip(keys,vals));rows.append({'params':params,'total_return':float(i+1)/1000.0,'max_drawdown':float((i%7)+1)/10000.0,'profit_factor':1.0+float(i%11)/100.0,'trades':10+i})
 return rows
def validation_rows(train,k):
 top=rank_train(train)[:k]
 return [{'params':clone(row['params']),'total_return':0.01+i/1000.0,'max_drawdown':0.001,'profit_factor':1.1,'trades':20+i} for i,row in enumerate(top)]
def completed_artifact(state,plan,task):
 train=result_rows(state,task);model=next(m for m in plan['models'] if m['model_id']==task['model_id']);k=min(plan['top_k_train'],model['grid_combinations']);validation=validation_rows(train,k);return task_result_payload(state,plan,task['task_identity'],status='COMPLETED',train_results=train,validation_results=validation)
def main():
 n7=load_n7_context(PLAN,FREEZE,LOCK);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json')
 # B1: stale lock pathname does not block; active advisory lock does.
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/'run';root.mkdir();(root/'.n10-state.lock').write_text('stale-file')
  with _run_lock(root): rejected(lambda: _run_lock(root).__enter__(),'run_state_lock_held')
  with _run_lock(root): pass
 # Core recovery/fencing/selection/authority matrix.
 with tempfile.TemporaryDirectory() as td:
  repo,manifest,authority=context(td,n7,n8);root=Path(td)/'run';state=initialize_run(root,manifest,n7.plan,n7=n7,n8=n8,repo_root=repo);assert len(unfinished_task_ids(root,manifest,n7.plan))==216
  tasks=sorted(n7.plan['tasks'],key=lambda r:r['task_identity']);first,second=tasks[:2]
  claim_task(root,manifest,n7.plan,first['task_identity'],owner='A',authority=authority);state_a=load_run(root,manifest,n7.plan);old=completed_artifact(state_a,n7.plan,first);old_attempt=old['attempt_id']
  raw=json.loads((root/'run_state.json').read_text());raw['tasks'][first['task_identity']]['lease_expires_at']=0;(root/'run_state.json').write_text(json.dumps(raw));claim_task(root,manifest,n7.plan,first['task_identity'],owner='B',authority=authority);state_b=load_run(root,manifest,n7.plan);assert state_b['tasks'][first['task_identity']]['attempt_id']!=old_attempt
  rejected(lambda:complete_task(root,manifest,n7.plan,old,authority=authority),'task_artifact_provenance_mismatch')
  current=completed_artifact(state_b,n7.plan,first);complete_task(root,manifest,n7.plan,current,authority=authority)
  # Source HEAD drift and dirty tree block execution-capable paths.
  (repo/'README').write_text('commit2');subprocess.check_call(['git','-C',str(repo),'add','README']);subprocess.check_call(['git','-C',str(repo),'commit','-q','-m','drift']);rejected(lambda:claim_task(root,manifest,n7.plan,second['task_identity'],authority=authority),'current_n9_authority_not_authorized')
  subprocess.check_call(['git','-C',str(repo),'reset','--hard','HEAD~1'],stdout=subprocess.DEVNULL);(repo/'dirty').write_text('x');rejected(lambda:claim_task(root,manifest,n7.plan,second['task_identity'],authority=authority),'current_n9_authority_not_authorized');(repo/'dirty').unlink()
  # Current torn artifact reconciles under public locked load.
  claim_task(root,manifest,n7.plan,second['task_identity'],owner='T',authority=authority);s=load_run(root,manifest,n7.plan);torn=completed_artifact(s,n7.plan,second);_write_new(_task_path(root,second['task_identity']),torn);rec=load_run(root,manifest,n7.plan);assert rec['tasks'][second['task_identity']]['status']=='COMPLETED'
  # Selection evidence: forged top-k or validation binding rejected even with recomputed result_hash.
  task=tasks[2];claim_task(root,manifest,n7.plan,task['task_identity'],owner='S',authority=authority);s=load_run(root,manifest,n7.plan);good=completed_artifact(s,n7.plan,task)
  bad=clone(good);bad['selected_train_top_k']=list(reversed(bad['selected_train_top_k']));bad['result_hash']=_hash({k:v for k,v in bad.items() if k not in {'started_at','ended_at','result_hash'}});rejected(lambda:validate_task_artifact(bad,s,task),'completed_task_result_incomplete')
  bad=clone(good);ranked=rank_train(bad['train_results']);top_keys={json.dumps(r['params'],sort_keys=True) for r in ranked[:len(bad['validation_results'])]};non_top=next(r for r in bad['train_results'] if json.dumps(r['params'],sort_keys=True) not in top_keys);bad['validation_results'][0]['params']=clone(non_top['params']);bad['result_hash']=_hash({k:v for k,v in bad.items() if k not in {'started_at','ended_at','result_hash'}});rejected(lambda:validate_task_artifact(bad,s,task),'completed_validation_top_k_mismatch')
  bad=clone(good);bad['validation_result_identities'][0]='0'*64;bad['result_hash']=_hash({k:v for k,v in bad.items() if k not in {'started_at','ended_at','result_hash'}});rejected(lambda:validate_task_artifact(bad,s,task),'completed_task_result_incomplete')
  # FAILED retry preserves evidence.
  task=tasks[3];claim_task(root,manifest,n7.plan,task['task_identity'],authority=authority);fail_task(root,manifest,n7.plan,task['task_identity'],'SyntheticError','boom',authority=authority);claim_task(root,manifest,n7.plan,task['task_identity'],owner='retry',authority=authority);hist=load_run(root,manifest,n7.plan)['tasks'][task['task_identity']]['attempts'];assert any(x['status']=='FAILED' for x in hist) and any(x['status']=='RETRY_AUTHORIZED' for x in hist)
 # Full 216-task synthetic recovery/finalization.
 with tempfile.TemporaryDirectory() as td:
  repo,manifest,authority=context(td,n7,n8,'N10_FULL.json');root=Path(td)/'full';initialize_run(root,manifest,n7.plan,n7=n7,n8=n8,repo_root=repo)
  for task in reversed(n7.plan['tasks']):
   claim_task(root,manifest,n7.plan,task['task_identity'],authority=authority);s=load_run(root,manifest,n7.plan);complete_task(root,manifest,n7.plan,completed_artifact(s,n7.plan,task),authority=authority)
  assert final_result_identity(root,manifest,n7.plan) and not unfinished_task_ids(root,manifest,n7.plan)
 print('RECOVERABLE_EXECUTION_SYNTHETIC_TEST_OK')
if __name__=='__main__': main()
