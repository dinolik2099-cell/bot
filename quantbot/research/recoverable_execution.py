"""N10 crash-safe state layer for a future, already-authorized formal run.

This module intentionally contains no data loader, evaluator, or OOS pathway.
It persists only identity-bound task state and result metadata.
"""
from __future__ import annotations
import hashlib,json,os,re,time
from pathlib import Path
from typing import Mapping

SCHEMA='quantbot-recoverable-execution-n10-v1'
TASK_STATES={'PENDING','RUNNING','COMPLETED','FAILED'}
class RecoverableExecutionError(RuntimeError): pass
def _canon(value): return json.dumps(value,sort_keys=True,separators=(',',':'))
def _hash(value): return hashlib.sha256(_canon(value).encode()).hexdigest()
def _write_new(path,value):
 path=Path(path)
 if path.exists(): raise RecoverableExecutionError('immutable_artifact_exists')
 path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
 try:
  temp.write_text(_canon(value)+'\n',encoding='utf-8')
  os.replace(temp,path)
 except Exception:
  temp.unlink(missing_ok=True);raise
def _replace(path,value):
 path=Path(path);temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
 temp.write_text(_canon(value)+'\n',encoding='utf-8');os.replace(temp,path)
def _read(path):
 try:return json.loads(Path(path).read_text(encoding='utf-8'))
 except Exception as exc:raise RecoverableExecutionError('artifact_unreadable') from exc
def execution_binding(manifest,plan):
 """The complete immutable authority for an N10 run identity."""
 required=('manifest_identity','research_freeze_identity','research_plan_identity','candidate_universe_hash','dataset_id','boundary','boundary_identity_hash','engine','cost_model','adapter','source_git_commit','worker_config','ranking','top_k_train','viability','tasks','counts','oos_status','oos_authorization')
 if not isinstance(manifest,Mapping) or any(key not in manifest for key in required): raise RecoverableExecutionError('manifest_binding_incomplete')
 if manifest['oos_status']!='SEALED' or manifest['oos_authorization']!='NOT_AUTHORIZED': raise RecoverableExecutionError('oos_not_sealed')
 for key in ('research_freeze_identity','research_plan_identity','candidate_universe_hash','boundary','boundary_identity_hash','tasks','counts','ranking','top_k_train','viability'):
  if manifest[key]!=plan.get(key): raise RecoverableExecutionError('manifest_plan_binding_mismatch')
 if not isinstance(plan.get('models'),list): raise RecoverableExecutionError('plan_models_missing')
 return {key:manifest[key] for key in required}|{'models':plan['models'],'schema_version':SCHEMA}
def run_id(manifest,plan): return _hash(execution_binding(manifest,plan))
def _task_path(root,task_identity):
 if not isinstance(task_identity,str) or not re.fullmatch(r'[0-9a-f]{64}',task_identity): raise RecoverableExecutionError('task_identity_invalid')
 return Path(root)/'tasks'/f'{task_identity}.json'
def _task_index(plan):
 tasks=plan.get('tasks')
 if not isinstance(tasks,list) or len(tasks)!=plan.get('counts',{}).get('model_symbol_cells') or len(tasks)!=216: raise RecoverableExecutionError('frozen_task_universe_invalid')
 index={task.get('task_identity'):task for task in tasks}
 if len(index)!=len(tasks) or any(not key for key in index): raise RecoverableExecutionError('frozen_task_universe_invalid')
 return index
def _refresh_accounting(state,plan):
 records=state['tasks'];counts=plan['counts']
 state['accounting']={'expected_task_count':len(records),'completed_count':sum(row['status']=='COMPLETED' for row in records.values()),'failed_count':sum(row['status']=='FAILED' for row in records.values()),'pending_count':sum(row['status']=='PENDING' for row in records.values()),'running_count':sum(row['status']=='RUNNING' for row in records.values()),'total_expected_train_evaluations':counts['train_evaluations'],'total_completed_train_evaluations':sum(row.get('actual_train_evaluations',0) for row in records.values()),'max_allowed_validation_evaluations':counts['validation_evaluations_max'],'completed_validation_evaluations':sum(row.get('actual_validation_evaluations',0) for row in records.values())}
 return state
def initialize_run(root,manifest,plan):
 """Create one immutable 216-task run state; never overwrite an existing run."""
 binding=execution_binding(manifest,plan);tasks=_task_index(plan);rid=_hash(binding)
 state={'schema_version':SCHEMA,'run_id':rid,'binding':binding,'expected_task_count':len(tasks),'tasks':{key:{'status':'PENDING'} for key in sorted(tasks)},'created_at':time.time()};_refresh_accounting(state,plan)
 _write_new(Path(root)/'run_state.json',state)
 return state
def _validate_state(state,manifest,plan):
 binding=execution_binding(manifest,plan);tasks=_task_index(plan)
 if state.get('schema_version')!=SCHEMA or state.get('binding')!=binding or state.get('run_id')!=_hash(binding): raise RecoverableExecutionError('run_identity_or_provenance_drift')
 records=state.get('tasks')
 if not isinstance(records,dict) or set(records)!=set(tasks): raise RecoverableExecutionError('run_task_universe_drift')
 if any(record.get('status') not in TASK_STATES for record in records.values()): raise RecoverableExecutionError('run_task_state_invalid')
 expected={'tasks':json.loads(_canon(records))};_refresh_accounting(expected,plan)
 if state.get('accounting')!=expected['accounting']: raise RecoverableExecutionError('run_accounting_drift')
 return tasks
def load_run(root,manifest,plan):
 state=_read(Path(root)/'run_state.json');tasks=_validate_state(state,manifest,plan)
 for task_identity,record in state['tasks'].items():
  path=_task_path(root,task_identity)
  if record['status']=='COMPLETED':
   if not path.exists(): raise RecoverableExecutionError('completed_artifact_missing')
   validate_task_artifact(_read(path),state,tasks[task_identity])
  elif path.exists(): raise RecoverableExecutionError('noncompleted_task_has_artifact')
 return state
def unfinished_task_ids(root,manifest,plan):
 state=load_run(root,manifest,plan)
 return [key for key in sorted(state['tasks']) if state['tasks'][key]['status']!='COMPLETED']
def claim_task(root,manifest,plan,task_identity):
 state=load_run(root,manifest,plan);tasks=_validate_state(state,manifest,plan)
 if task_identity not in tasks: raise RecoverableExecutionError('unknown_task')
 record=state['tasks'][task_identity]
 if record['status']=='COMPLETED': raise RecoverableExecutionError('completed_task_cannot_recompute')
 if record['status']=='RUNNING': raise RecoverableExecutionError('task_already_running')
 record.update({'status':'RUNNING','started_at':time.time()});_refresh_accounting(state,plan);_replace(Path(root)/'run_state.json',state);return tasks[task_identity]
def _model(plan,model_id):
 rows=[row for row in plan.get('models',[]) if row.get('model_id')==model_id]
 if len(rows)!=1: raise RecoverableExecutionError('task_model_not_frozen')
 return rows[0]
def task_result_payload(state,plan,task_identity,*,status,train_evaluations=0,validation_evaluations=0,selected_train_top_k=(),error_type=None,error_message=None):
 tasks=_task_index(plan);task=tasks.get(task_identity)
 if task is None: raise RecoverableExecutionError('unknown_task')
 model=_model(plan,task['model_id']);expected_train=model.get('grid_combinations');expected_validation=min(plan['top_k_train'],expected_train)
 if status not in {'COMPLETED','FAILED'}: raise RecoverableExecutionError('task_terminal_state_invalid')
 body={'schema_version':SCHEMA,'run_id':state['run_id'],'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'manifest_identity':state['binding']['manifest_identity'],'task_identity':task_identity,'model_id':task['model_id'],'symbol':task['symbol'],'parameter_grid_hash':model['parameter_grid_hash'],'expected_train_evaluations':expected_train,'actual_train_evaluations':train_evaluations,'selected_train_top_k':list(selected_train_top_k),'expected_validation_evaluations':expected_validation,'actual_validation_evaluations':validation_evaluations,'status':status,'error_type':error_type,'error_message':error_message,'started_at':state['tasks'][task_identity].get('started_at'),'ended_at':time.time()}
 body['result_hash']=_hash({key:value for key,value in body.items() if key not in {'started_at','ended_at','result_hash'}})
 return body
def validate_task_artifact(artifact,state,task):
 model=_model_from_state_task(state,task)
 required={'schema_version':SCHEMA,'run_id':state['run_id'],'research_freeze_identity':state['binding']['research_freeze_identity'],'research_plan_identity':state['binding']['research_plan_identity'],'manifest_identity':state['binding']['manifest_identity'],'task_identity':task['task_identity'],'model_id':task['model_id'],'symbol':task['symbol'],'parameter_grid_hash':model['parameter_grid_hash']}
 if any(artifact.get(key)!=value for key,value in required.items()): raise RecoverableExecutionError('task_artifact_provenance_mismatch')
 status=artifact.get('status');expected_train=model['grid_combinations'];expected_validation=min(state['binding']['top_k_train'],expected_train)
 if status=='COMPLETED':
  if artifact.get('actual_train_evaluations')!=expected_train or artifact.get('expected_train_evaluations')!=expected_train or artifact.get('actual_validation_evaluations')!=expected_validation or artifact.get('expected_validation_evaluations')!=expected_validation or len(artifact.get('selected_train_top_k',[]))!=expected_validation or artifact.get('error_type') or artifact.get('error_message'): raise RecoverableExecutionError('completed_task_result_incomplete')
 elif status=='FAILED':
  if not isinstance(artifact.get('error_type'),str) or not artifact['error_type'] or not isinstance(artifact.get('error_message'),str) or artifact.get('actual_train_evaluations') or artifact.get('actual_validation_evaluations') or artifact.get('selected_train_top_k'): raise RecoverableExecutionError('failed_task_result_invalid')
 else: raise RecoverableExecutionError('task_artifact_state_invalid')
 payload={key:value for key,value in artifact.items() if key not in {'started_at','ended_at','result_hash'}}
 if artifact.get('result_hash')!=_hash(payload): raise RecoverableExecutionError('task_result_hash_mismatch')
 return True
def _model_from_state_task(state,task):
 # The immutable binding carries the exact plan task universe but models are
 # supplied by the caller only when creating an artifact; this helper uses its
 # embedded per-task frozen grid count established during initialization.
 models=state['binding'].get('models')
 if not isinstance(models,list): raise RecoverableExecutionError('run_model_binding_missing')
 rows=[row for row in models if row.get('model_id')==task['model_id']]
 if len(rows)!=1: raise RecoverableExecutionError('task_model_not_frozen')
 return rows[0]
def complete_task(root,manifest,plan,artifact):
 state=load_run(root,manifest,plan);tasks=_validate_state(state,manifest,plan);task=tasks.get(artifact.get('task_identity'))
 if task is None: raise RecoverableExecutionError('unknown_task')
 if state['tasks'][task['task_identity']]['status']!='RUNNING': raise RecoverableExecutionError('task_not_running')
 validate_task_artifact(artifact,state,task)
 if artifact['status']!='COMPLETED': raise RecoverableExecutionError('complete_requires_completed_artifact')
 _write_new(_task_path(root,task['task_identity']),artifact);state['tasks'][task['task_identity']]={'status':'COMPLETED','result_hash':artifact['result_hash'],'actual_train_evaluations':artifact['actual_train_evaluations'],'actual_validation_evaluations':artifact['actual_validation_evaluations']};_refresh_accounting(state,plan);_replace(Path(root)/'run_state.json',state)
def fail_task(root,manifest,plan,task_identity,error_type,error_message):
 state=load_run(root,manifest,plan);tasks=_validate_state(state,manifest,plan)
 if task_identity not in tasks or state['tasks'][task_identity]['status']!='RUNNING': raise RecoverableExecutionError('task_not_running')
 artifact=task_result_payload(state,plan,task_identity,status='FAILED',error_type=error_type,error_message=error_message)
 validate_task_artifact(artifact,state,tasks[task_identity]);state['tasks'][task_identity]={'status':'FAILED','error_type':error_type,'error_message':error_message};_refresh_accounting(state,plan);_replace(Path(root)/'run_state.json',state)
def final_result_identity(root,manifest,plan):
 state=load_run(root,manifest,plan)
 if any(record['status']!='COMPLETED' for record in state['tasks'].values()): raise RecoverableExecutionError('partial_run_cannot_finalize')
 rows=[_read(_task_path(root,key)) for key in sorted(state['tasks'])]
 return _hash({'run_id':state['run_id'],'task_result_hashes':[(row['task_identity'],row['result_hash']) for row in rows]})
