"""Synthetic-only N10 state/recovery adversarial contract tests."""
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest
from quantbot.research.recoverable_execution import (RecoverableExecutionError,initialize_run,load_run,unfinished_task_ids,claim_task,task_result_payload,complete_task,fail_task,final_result_identity)
LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'
def clone(value): return json.loads(json.dumps(value))
def rejected(fn):
 try: fn()
 except RecoverableExecutionError:return
 raise AssertionError('unexpectedly accepted')
def main():
 n7=load_n7_context(PLAN,FREEZE,LOCK);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json')
 manifest=build_manifest(n7,n8,source_git_commit='f'*40,worker_config={'workers':2},output_destination='data/reports/formal_runs/N10_RESULT.json',created_at='synthetic')
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/'run';state=initialize_run(root,manifest,n7.plan);assert state['expected_task_count']==216 and len(unfinished_task_ids(root,manifest,n7.plan))==216
  first=sorted(n7.plan['tasks'],key=lambda row:row['task_identity'])[0];claim_task(root,manifest,n7.plan,first['task_identity']);state=load_run(root,manifest,n7.plan)
  model=next(row for row in n7.plan['models'] if row['model_id']==first['model_id']);top=[f'top-{index}' for index in range(min(n7.plan['top_k_train'],model['grid_combinations']))]
  completed=task_result_payload(state,n7.plan,first['task_identity'],status='COMPLETED',train_evaluations=model['grid_combinations'],validation_evaluations=len(top),selected_train_top_k=top)
  complete_task(root,manifest,n7.plan,completed);assert len(unfinished_task_ids(root,manifest,n7.plan))==215
  rejected(lambda:complete_task(root,manifest,n7.plan,completed));rejected(lambda:claim_task(root,manifest,n7.plan,'0'*64))
  second=sorted(n7.plan['tasks'],key=lambda row:row['task_identity'])[1];claim_task(root,manifest,n7.plan,second['task_identity']);state=load_run(root,manifest,n7.plan);second_model=next(row for row in n7.plan['models'] if row['model_id']==second['model_id'])
  truncated=task_result_payload(state,n7.plan,second['task_identity'],status='COMPLETED',train_evaluations=second_model['grid_combinations']-1,validation_evaluations=min(n7.plan['top_k_train'],second_model['grid_combinations']),selected_train_top_k=['x']*min(n7.plan['top_k_train'],second_model['grid_combinations']))
  rejected(lambda:complete_task(root,manifest,n7.plan,truncated))
  failed_with_results=task_result_payload(state,n7.plan,second['task_identity'],status='FAILED',train_evaluations=1,error_type='Synthetic',error_message='must not contain results')
  rejected(lambda:complete_task(root,manifest,n7.plan,failed_with_results))
  changed_manifest=clone(manifest);changed_manifest['worker_config']['workers']=3;rejected(lambda:load_run(root,changed_manifest,n7.plan))
  changed_plan=clone(n7.plan);changed_plan['ranking']='tampered';rejected(lambda:load_run(root,manifest,changed_plan))
  path=root/'tasks'/f"{first['task_identity']}.json";corrupt=json.loads(path.read_text());corrupt['result_hash']='0'*64;path.write_text(json.dumps(corrupt));rejected(lambda:load_run(root,manifest,n7.plan))
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/'full';initialize_run(root,manifest,n7.plan)
  for task in reversed(n7.plan['tasks']):
   claim_task(root,manifest,n7.plan,task['task_identity']);state=load_run(root,manifest,n7.plan);model=next(row for row in n7.plan['models'] if row['model_id']==task['model_id']);top=[f'{task["task_identity"]}:{index}' for index in range(min(n7.plan['top_k_train'],model['grid_combinations']))]
   complete_task(root,manifest,n7.plan,task_result_payload(state,n7.plan,task['task_identity'],status='COMPLETED',train_evaluations=model['grid_combinations'],validation_evaluations=len(top),selected_train_top_k=top))
  one=final_result_identity(root,manifest,n7.plan);assert one and not unfinished_task_ids(root,manifest,n7.plan)
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/'failed';initialize_run(root,manifest,n7.plan);task=n7.plan['tasks'][0];claim_task(root,manifest,n7.plan,task['task_identity']);fail_task(root,manifest,n7.plan,task['task_identity'],'SyntheticError','synthetic failure');assert task['task_identity'] in unfinished_task_ids(root,manifest,n7.plan);rejected(lambda:final_result_identity(root,manifest,n7.plan))
 print('RECOVERABLE_EXECUTION_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
