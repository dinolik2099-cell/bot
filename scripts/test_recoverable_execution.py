"""Synthetic-only N10 state/recovery adversarial contract tests."""
from pathlib import Path
import json,sys,tempfile,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest
from quantbot.research.recoverable_execution import (RecoverableExecutionError,initialize_run,load_run,unfinished_task_ids,claim_task,task_result_payload,complete_task,fail_task,final_result_identity,_expected_train_ids,_task_path,_write_new)
LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'
def clone(value): return json.loads(json.dumps(value))
def rejected(fn):
 try: fn()
 except RecoverableExecutionError:return
 raise AssertionError('unexpectedly accepted')
def clean_repo(path):
 subprocess.check_call(['git','init','-q',str(path)]);subprocess.check_call(['git','-C',str(path),'config','user.email','n10@example.invalid']);subprocess.check_call(['git','-C',str(path),'config','user.name','N10']);(path/'README').write_text('n10');subprocess.check_call(['git','-C',str(path),'add','README']);subprocess.check_call(['git','-C',str(path),'commit','-q','-m','n10']);return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
def main():
 n7=load_n7_context(PLAN,FREEZE,LOCK);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json')
 with tempfile.TemporaryDirectory() as td:
  repo=Path(td)/'repo';repo.mkdir();commit=clean_repo(repo);manifest=build_manifest(n7,n8,source_git_commit=commit,worker_config={'workers':2},output_destination='data/reports/formal_runs/N10_RESULT.json',created_at='synthetic')
  authority={'n7':n7,'n8':n8,'repo_root':repo,'requested_windows':{'TRAIN':manifest['train_window'],'VALIDATION':manifest['validation_window']},'output_path':manifest['output']['destination'],'requested_workers':2}
  root=Path(td)/'run';state=initialize_run(root,manifest,n7.plan,n7=n7,n8=n8,repo_root=repo);assert state['expected_task_count']==216 and len(unfinished_task_ids(root,manifest,n7.plan))==216
  forged=clone(manifest);forged['adapter']['implementation_hash']='0'*64;rejected(lambda:initialize_run(Path(td)/'forged',forged,n7.plan,n7=n7,n8=n8,repo_root=repo))
  source_drift=build_manifest(n7,n8,source_git_commit='0'*40,worker_config={'workers':2},output_destination='data/reports/formal_runs/N10_RESULT.json',created_at='synthetic');rejected(lambda:initialize_run(Path(td)/'source-drift',source_drift,n7.plan,n7=n7,n8=n8,repo_root=repo))
  first=sorted(n7.plan['tasks'],key=lambda row:row['task_identity'])[0];claim_task(root,manifest,n7.plan,first['task_identity'],authority=authority);state=load_run(root,manifest,n7.plan)
  model=next(row for row in n7.plan['models'] if row['model_id']==first['model_id']);top=[f'top-{index}' for index in range(min(n7.plan['top_k_train'],model['grid_combinations']))]
  train_ids=_expected_train_ids(state,first);completed=task_result_payload(state,n7.plan,first['task_identity'],status='COMPLETED',train_evaluations=model['grid_combinations'],validation_evaluations=len(top),train_result_identities=train_ids,selected_train_top_k=train_ids[:len(top)],validation_result_identities=[f'validation-{i}' for i in range(len(top))])
  complete_task(root,manifest,n7.plan,completed,authority=authority);assert len(unfinished_task_ids(root,manifest,n7.plan))==215
  rejected(lambda:complete_task(root,manifest,n7.plan,completed,authority=authority));rejected(lambda:claim_task(root,manifest,n7.plan,'0'*64,authority=authority))
  second=sorted(n7.plan['tasks'],key=lambda row:row['task_identity'])[1];claim_task(root,manifest,n7.plan,second['task_identity'],authority=authority);state=load_run(root,manifest,n7.plan);second_model=next(row for row in n7.plan['models'] if row['model_id']==second['model_id'])
  rejected(lambda:claim_task(root,manifest,n7.plan,second['task_identity'],authority=authority))
  state_path=root/'run_state.json';crashed=json.loads(state_path.read_text());crashed['tasks'][second['task_identity']]['lease_expires_at']=0;state_path.write_text(json.dumps(crashed));claim_task(root,manifest,n7.plan,second['task_identity'],owner='recovery',authority=authority);state=load_run(root,manifest,n7.plan);assert any(item['status']=='STALE_RECOVERED' for item in state['tasks'][second['task_identity']]['attempts'])
  good=json.loads(state_path.read_text());bad=clone(good);bad['revision']='tampered';state_path.write_text(json.dumps(bad));rejected(lambda:load_run(root,manifest,n7.plan));state_path.write_text(json.dumps(good))
  k=min(n7.plan['top_k_train'],second_model['grid_combinations']);train_ids=_expected_train_ids(state,second);torn=task_result_payload(state,n7.plan,second['task_identity'],status='COMPLETED',train_evaluations=second_model['grid_combinations'],validation_evaluations=k,train_result_identities=train_ids,selected_train_top_k=train_ids[:k],validation_result_identities=[f'torn-{i}' for i in range(k)])
  _write_new(_task_path(root,second['task_identity']),torn);reconciled=load_run(root,manifest,n7.plan);assert reconciled['tasks'][second['task_identity']]['status']=='COMPLETED'
  truncated=task_result_payload(state,n7.plan,second['task_identity'],status='COMPLETED',train_evaluations=second_model['grid_combinations']-1,validation_evaluations=min(n7.plan['top_k_train'],second_model['grid_combinations']),selected_train_top_k=['x']*min(n7.plan['top_k_train'],second_model['grid_combinations']))
  rejected(lambda:complete_task(root,manifest,n7.plan,truncated,authority=authority))
  expected_ids=_expected_train_ids(state,second)
  def bad_complete(train_ids,top_ids,validation_ids): return task_result_payload(state,n7.plan,second['task_identity'],status='COMPLETED',train_evaluations=second_model['grid_combinations'],validation_evaluations=k,train_result_identities=train_ids,selected_train_top_k=top_ids,validation_result_identities=validation_ids)
  rejected(lambda:complete_task(root,manifest,n7.plan,bad_complete(expected_ids[:-1],expected_ids[:k],['v'+str(i) for i in range(k)]),authority=authority))
  rejected(lambda:complete_task(root,manifest,n7.plan,bad_complete(expected_ids[:-1]+['unknown'],expected_ids[:k],['v'+str(i) for i in range(k)]),authority=authority))
  rejected(lambda:complete_task(root,manifest,n7.plan,bad_complete([expected_ids[0]]*len(expected_ids),expected_ids[:k],['v'+str(i) for i in range(k)]),authority=authority))
  rejected(lambda:complete_task(root,manifest,n7.plan,bad_complete(expected_ids,['not-train']*k,['v'+str(i) for i in range(k)]),authority=authority))
  rejected(lambda:complete_task(root,manifest,n7.plan,bad_complete(expected_ids,expected_ids[:k],['v']*k),authority=authority))
  failed_with_results=task_result_payload(state,n7.plan,second['task_identity'],status='FAILED',train_evaluations=1,error_type='Synthetic',error_message='must not contain results')
  rejected(lambda:complete_task(root,manifest,n7.plan,failed_with_results,authority=authority))
  changed_manifest=clone(manifest);changed_manifest['worker_config']['workers']=3;rejected(lambda:load_run(root,changed_manifest,n7.plan))
  changed_plan=clone(n7.plan);changed_plan['ranking']='tampered';rejected(lambda:load_run(root,manifest,changed_plan))
  path=root/'tasks'/f"{first['task_identity']}.json";corrupt=json.loads(path.read_text());corrupt['result_hash']='0'*64;path.write_text(json.dumps(corrupt));rejected(lambda:load_run(root,manifest,n7.plan))
 with tempfile.TemporaryDirectory() as td:
  repo=Path(td)/'repo';repo.mkdir();local_manifest=build_manifest(n7,n8,source_git_commit=clean_repo(repo),worker_config={'workers':2},output_destination='data/reports/formal_runs/N10_RESULT.json',created_at='synthetic')
  local_authority={'n7':n7,'n8':n8,'repo_root':repo,'requested_windows':{'TRAIN':local_manifest['train_window'],'VALIDATION':local_manifest['validation_window']},'output_path':local_manifest['output']['destination'],'requested_workers':2}
  root=Path(td)/'full';initialize_run(root,local_manifest,n7.plan,n7=n7,n8=n8,repo_root=repo)
  for task in reversed(n7.plan['tasks']):
   claim_task(root,local_manifest,n7.plan,task['task_identity'],authority=local_authority);state=load_run(root,local_manifest,n7.plan);model=next(row for row in n7.plan['models'] if row['model_id']==task['model_id']);top=[f'{task["task_identity"]}:{index}' for index in range(min(n7.plan['top_k_train'],model['grid_combinations']))]
   train_ids=_expected_train_ids(state,task);complete_task(root,local_manifest,n7.plan,task_result_payload(state,n7.plan,task['task_identity'],status='COMPLETED',train_evaluations=model['grid_combinations'],validation_evaluations=len(top),train_result_identities=train_ids,selected_train_top_k=train_ids[:len(top)],validation_result_identities=[f'{task["task_identity"]}-validation-{i}' for i in range(len(top))]),authority=local_authority)
  one=final_result_identity(root,local_manifest,n7.plan);assert one and not unfinished_task_ids(root,local_manifest,n7.plan)
 with tempfile.TemporaryDirectory() as td:
  repo=Path(td)/'repo';repo.mkdir();local_manifest=build_manifest(n7,n8,source_git_commit=clean_repo(repo),worker_config={'workers':2},output_destination='data/reports/formal_runs/N10_RESULT.json',created_at='synthetic')
  local_authority={'n7':n7,'n8':n8,'repo_root':repo,'requested_windows':{'TRAIN':local_manifest['train_window'],'VALIDATION':local_manifest['validation_window']},'output_path':local_manifest['output']['destination'],'requested_workers':2}
  root=Path(td)/'failed';initialize_run(root,local_manifest,n7.plan,n7=n7,n8=n8,repo_root=repo);task=n7.plan['tasks'][0];claim_task(root,local_manifest,n7.plan,task['task_identity'],authority=local_authority);fail_task(root,local_manifest,n7.plan,task['task_identity'],'SyntheticError','synthetic failure',authority=local_authority);failed=load_run(root,local_manifest,n7.plan);assert any(item['status']=='FAILED' and item['error_message']=='synthetic failure' for item in failed['tasks'][task['task_identity']]['attempts']);claim_task(root,local_manifest,n7.plan,task['task_identity'],owner='retry',authority=local_authority);retried=load_run(root,local_manifest,n7.plan);history=retried['tasks'][task['task_identity']]['attempts'];assert any(item['status']=='FAILED' for item in history) and any(item['status']=='RETRY_AUTHORIZED' for item in history);assert task['task_identity'] in unfinished_task_ids(root,local_manifest,n7.plan);rejected(lambda:final_result_identity(root,local_manifest,n7.plan))
 print('RECOVERABLE_EXECUTION_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
