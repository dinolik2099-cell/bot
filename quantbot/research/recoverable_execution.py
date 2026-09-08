"""N10 crash-safe state layer for a future, already-authorized formal run.

This module intentionally contains no data loader, evaluator, or OOS pathway.
It persists only identity-bound task state and result metadata.
"""
from __future__ import annotations
import hashlib,json,os,re,time,uuid
from itertools import product
from contextlib import contextmanager
from pathlib import Path
from typing import Mapping

SCHEMA='quantbot-recoverable-execution-n10-v2'
TASK_STATES={'PENDING','RUNNING','COMPLETED','FAILED'}
class RecoverableExecutionError(RuntimeError): pass
def authorize_execution_context(manifest,*,n7,n8,repo_root,requested_windows,output_path,requested_workers):
 """Revalidate current N9 authority before any execution-capable transition."""
 try:
  from .formal_execution_manifest import validate_manifest,preflight_authorize
  validate_manifest(manifest,n7,n8)
  return preflight_authorize(manifest,n7,n8,repo_root=repo_root,requested_windows=requested_windows,output_path=output_path,requested_workers=requested_workers)
 except Exception as exc: raise RecoverableExecutionError('current_n9_authority_not_authorized') from exc
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
LOCK_WAIT_SECONDS=30.0
@contextmanager
def _run_lock(root, wait_seconds=LOCK_WAIT_SECONDS):
 """Kernel-backed advisory lock with bounded retry/backoff.

 Normal worker contention waits for the state serializer rather than being
 misclassified as a task failure.  A missing/held lock still fails closed after
 a bounded deadline; fencing and immutable artifacts remain unchanged.
 """
 lock=Path(root)/'.n10-state.lock';lock.parent.mkdir(parents=True,exist_ok=True)
 handle=lock.open('a+b')
 deadline=time.monotonic()+float(wait_seconds);delay=.01
 while True:
  try:
   if os.name=='nt':
    import msvcrt
    handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   break
  except OSError as exc:
   if time.monotonic()>=deadline:
    handle.close();raise RecoverableExecutionError('run_state_lock_timeout') from exc
   time.sleep(delay);delay=min(delay*2,.25)
 try: yield
 finally:
  try:
   if os.name=='nt':
    import msvcrt
    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
   else:
    import fcntl
    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
  finally: handle.close()
def _bump(state): state['revision']=int(state.get('revision',0))+1;return state
def _read(path):
 try:return json.loads(Path(path).read_text(encoding='utf-8'))
 except Exception as exc:raise RecoverableExecutionError('artifact_unreadable') from exc
def execution_binding(manifest,plan,*,n7=None,n8=None):
 """The complete immutable authority for an N10 run identity."""
 required=('manifest_identity','research_freeze_identity','research_plan_identity','candidate_universe_hash','dataset_id','boundary','boundary_identity_hash','engine','cost_model','adapter','source_git_commit','worker_config','ranking','top_k_train','viability','tasks','counts','oos_status','oos_authorization')
 if (n7 is None)!=(n8 is None): raise RecoverableExecutionError('accepted_n9_context_incomplete')
 if n7 is not None:
  try:
   from .formal_execution_manifest import validate_manifest
   validate_manifest(manifest,n7,n8)
  except Exception as exc: raise RecoverableExecutionError('n9_manifest_not_accepted') from exc
 if not isinstance(manifest,Mapping) or any(key not in manifest for key in required): raise RecoverableExecutionError('manifest_binding_incomplete')
 if manifest['oos_status']!='SEALED' or manifest['oos_authorization']!='NOT_AUTHORIZED': raise RecoverableExecutionError('oos_not_sealed')
 for key in ('research_freeze_identity','research_plan_identity','candidate_universe_hash','boundary','boundary_identity_hash','tasks','counts','ranking','top_k_train','viability'):
  if manifest[key]!=plan.get(key): raise RecoverableExecutionError('manifest_plan_binding_mismatch')
 if not isinstance(plan.get('models'),list): raise RecoverableExecutionError('plan_models_missing')
 grids={entry.model_id:{key:list(values) for key,values in sorted(entry.parameter_grid.items())} for entry in getattr(n7,'entries',())}
 if n7 is not None and set(grids)!={row['model_id'] for row in plan['models']}: raise RecoverableExecutionError('frozen_grid_binding_mismatch')
 return {key:manifest[key] for key in required}|{'models':plan['models'],'parameter_grids':grids,'schema_version':SCHEMA}
def run_id(manifest,plan,*,n7,n8): return _hash(execution_binding(manifest,plan,n7=n7,n8=n8))
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
def initialize_run(root,manifest,plan,*,n7,n8,repo_root):
 """Create one immutable 216-task run state; never overwrite an existing run."""
 binding=execution_binding(manifest,plan,n7=n7,n8=n8)
 try:
  authorize_execution_context(manifest,n7=n7,n8=n8,repo_root=repo_root,requested_windows={'TRAIN':manifest['train_window'],'VALIDATION':manifest['validation_window']},output_path=manifest['output']['destination'],requested_workers=manifest['worker_config']['workers'])
 except Exception as exc: raise RecoverableExecutionError('n9_preflight_not_authorized') from exc
 tasks=_task_index(plan);rid=_hash(binding)
 state={'schema_version':SCHEMA,'run_id':rid,'revision':0,'binding':binding,'expected_task_count':len(tasks),'tasks':{key:{'status':'PENDING','attempts':[]} for key in sorted(tasks)},'created_at':time.time()};_refresh_accounting(state,plan)
 with _run_lock(root): _write_new(Path(root)/'run_state.json',state)
 return state
def _validate_state(state,manifest,plan):
 binding=execution_binding(manifest,plan)
 if isinstance(state.get('binding'),dict) and 'parameter_grids' in state['binding']: binding['parameter_grids']=state['binding']['parameter_grids']
 tasks=_task_index(plan)
 if state.get('schema_version')!=SCHEMA or state.get('binding')!=binding or state.get('run_id')!=_hash(binding) or type(state.get('revision')) is not int or state['revision']<0: raise RecoverableExecutionError('run_identity_or_provenance_drift')
 records=state.get('tasks')
 if not isinstance(records,dict) or set(records)!=set(tasks): raise RecoverableExecutionError('run_task_universe_drift')
 if any(record.get('status') not in TASK_STATES for record in records.values()): raise RecoverableExecutionError('run_task_state_invalid')
 expected={'tasks':json.loads(_canon(records))};_refresh_accounting(expected,plan)
 if state.get('accounting')!=expected['accounting']: raise RecoverableExecutionError('run_accounting_drift')
 return tasks
def _load_run_locked(root,manifest,plan):
 """Load/validate and reconcile torn state. Caller MUST hold _run_lock(root)."""
 state=_read(Path(root)/'run_state.json');tasks=_validate_state(state,manifest,plan);reconciled=False
 for task_identity,record in state['tasks'].items():
  path=_task_path(root,task_identity)
  if record['status']=='COMPLETED':
   if not path.exists(): raise RecoverableExecutionError('completed_artifact_missing')
   validate_task_artifact(_read(path),state,tasks[task_identity])
  elif path.exists() and record['status']=='RUNNING':
   artifact=_read(path);validate_task_artifact(artifact,state,tasks[task_identity])
   if artifact['status']!='COMPLETED': raise RecoverableExecutionError('torn_task_artifact_invalid')
   state['tasks'][task_identity].update({'status':'COMPLETED','result_hash':artifact['result_hash'],'actual_train_evaluations':artifact['actual_train_evaluations'],'actual_validation_evaluations':artifact['actual_validation_evaluations']});reconciled=True
  elif path.exists(): raise RecoverableExecutionError('noncompleted_task_has_artifact')
 if reconciled: _refresh_accounting(state,plan);_bump(state);_replace(Path(root)/'run_state.json',state)
 return state

def load_run(root,manifest,plan):
 """Public load is serialized because validation may reconcile a torn commit."""
 with _run_lock(root): return _load_run_locked(root,manifest,plan)
def unfinished_task_ids(root,manifest,plan):
 state=load_run(root,manifest,plan)
 return [key for key in sorted(state['tasks']) if state['tasks'][key]['status']!='COMPLETED']
def claim_task(root,manifest,plan,task_identity,*,owner='local',lease_seconds=300,authority=None):
 if not isinstance(owner,str) or not owner or type(lease_seconds) is not int or lease_seconds<1: raise RecoverableExecutionError('claim_metadata_invalid')
 if not isinstance(authority,Mapping): raise RecoverableExecutionError('execution_authority_required')
 authorize_execution_context(manifest,n7=authority.get('n7'),n8=authority.get('n8'),repo_root=authority.get('repo_root'),requested_windows=authority.get('requested_windows'),output_path=authority.get('output_path'),requested_workers=authority.get('requested_workers'))
 with _run_lock(root): return _claim_task(root,manifest,plan,task_identity,owner,lease_seconds)
def _claim_task(root,manifest,plan,task_identity,owner,lease_seconds):
 state=_load_run_locked(root,manifest,plan);tasks=_validate_state(state,manifest,plan)
 if task_identity not in tasks: raise RecoverableExecutionError('unknown_task')
 record=state['tasks'][task_identity]
 if record['status']=='COMPLETED': raise RecoverableExecutionError('completed_task_cannot_recompute')
 now=time.time()
 if record['status']=='RUNNING' and record.get('lease_expires_at',now)>=now: raise RecoverableExecutionError('task_already_running')
 if record['status']=='RUNNING': record.setdefault('attempts',[]).append({'attempt_id':record.get('attempt_id'),'status':'STALE_RECOVERED','owner':record.get('owner'),'ended_at':now})
 if record['status']=='FAILED': record.setdefault('attempts',[]).append({'attempt_id':record.get('attempt_id'),'status':'RETRY_AUTHORIZED','ended_at':now,'error_type':record.get('error_type'),'error_message':record.get('error_message')})
 record.update({'status':'RUNNING','attempt_id':uuid.uuid4().hex,'owner':owner,'started_at':now,'lease_expires_at':now+lease_seconds});_refresh_accounting(state,plan);_bump(state);_replace(Path(root)/'run_state.json',state);return tasks[task_identity]
def _model(plan,model_id):
 rows=[row for row in plan.get('models',[]) if row.get('model_id')==model_id]
 if len(rows)!=1: raise RecoverableExecutionError('task_model_not_frozen')
 return rows[0]
def _params_key(params):
 if not isinstance(params,dict): raise RecoverableExecutionError('result_params_invalid')
 return _canon(params)
def _result_metrics(row):
 try:
  from .plan_executor import validate_metrics
  validate_metrics(row)
 except Exception as exc: raise RecoverableExecutionError('result_metrics_invalid') from exc
 return {key:row[key] for key in ('total_return','max_drawdown','profit_factor','trades')}
def _train_result_identity(state,task,row):
 model=_model_from_state_task(state,task)
 return _hash({'task_identity':task['task_identity'],'parameter_grid_hash':model['parameter_grid_hash'],'params':row['params'],'metrics':_result_metrics(row)})
def _ranked_train(state,task,train_results):
 try:
  from .plan_executor import rank_train
  ranked=rank_train(train_results)
 except Exception as exc: raise RecoverableExecutionError('train_ranking_invalid') from exc
 return ranked
def _validation_result_identity(state,task,selected_train_id,row):
 return _hash({'task_identity':task['task_identity'],'selected_train_result_identity':selected_train_id,'params':row['params'],'metrics':_result_metrics(row)})
def _derive_completed_evidence(state,task,train_results,validation_results):
 model=_model_from_state_task(state,task);grid=state['binding'].get('parameter_grids',{}).get(task['model_id'])
 if not isinstance(train_results,list) or not isinstance(validation_results,list) or not isinstance(grid,dict) or not grid: raise RecoverableExecutionError('completed_task_result_evidence_missing')
 keys=sorted(grid);expected_params=[dict(zip(keys,values)) for values in product(*(grid[key] for key in keys))]
 expected_keys=[_params_key(row) for row in expected_params];train_keys=[]
 for row in train_results:
  if not isinstance(row,dict) or 'params' not in row: raise RecoverableExecutionError('completed_train_result_invalid')
  _result_metrics(row);train_keys.append(_params_key(row['params']))
 if len(train_results)!=model['grid_combinations'] or len(train_keys)!=len(set(train_keys)) or set(train_keys)!=set(expected_keys): raise RecoverableExecutionError('completed_train_grid_mismatch')
 train_ids=[_train_result_identity(state,task,row) for row in train_results]
 if len(train_ids)!=len(set(train_ids)): raise RecoverableExecutionError('completed_train_identity_duplicate')
 id_by_params={_params_key(row['params']):rid for row,rid in zip(train_results,train_ids)}
 ranked=_ranked_train(state,task,train_results);k=min(state['binding']['top_k_train'],len(expected_params));selected=ranked[:k]
 selected_ids=[id_by_params[_params_key(row['params'])] for row in selected]
 if len(validation_results)!=k: raise RecoverableExecutionError('completed_validation_count_mismatch')
 validation_ids=[]
 for index,row in enumerate(validation_results):
  if not isinstance(row,dict) or 'params' not in row: raise RecoverableExecutionError('completed_validation_result_invalid')
  _result_metrics(row)
  if _params_key(row['params'])!=_params_key(selected[index]['params']): raise RecoverableExecutionError('completed_validation_top_k_mismatch')
  validation_ids.append(_validation_result_identity(state,task,selected_ids[index],row))
 if len(validation_ids)!=len(set(validation_ids)): raise RecoverableExecutionError('completed_validation_identity_duplicate')
 return train_ids,selected_ids,validation_ids

def task_result_payload(state,plan,task_identity,*,status,train_results=(),validation_results=(),error_type=None,error_message=None):
 tasks=_task_index(plan);task=tasks.get(task_identity)
 if task is None: raise RecoverableExecutionError('unknown_task')
 model=_model(plan,task['model_id']);expected_train=model.get('grid_combinations');expected_validation=min(plan['top_k_train'],expected_train)
 if status not in {'COMPLETED','FAILED'}: raise RecoverableExecutionError('task_terminal_state_invalid')
 train_results=list(train_results);validation_results=list(validation_results)
 train_ids=[];top_ids=[];validation_ids=[]
 if status=='COMPLETED': train_ids,top_ids,validation_ids=_derive_completed_evidence(state,task,train_results,validation_results)
 body={'schema_version':SCHEMA,'run_id':state['run_id'],'attempt_id':state['tasks'][task_identity].get('attempt_id'),'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'manifest_identity':state['binding']['manifest_identity'],'task_identity':task_identity,'model_id':task['model_id'],'symbol':task['symbol'],'parameter_grid_hash':model['parameter_grid_hash'],'expected_train_evaluations':expected_train,'actual_train_evaluations':len(train_results),'train_results':train_results,'train_result_identities':train_ids,'selected_train_top_k':top_ids,'expected_validation_evaluations':expected_validation,'actual_validation_evaluations':len(validation_results),'validation_results':validation_results,'validation_result_identities':validation_ids,'status':status,'error_type':error_type,'error_message':error_message,'started_at':state['tasks'][task_identity].get('started_at'),'ended_at':time.time()}
 body['result_hash']=_hash({key:value for key,value in body.items() if key not in {'started_at','ended_at','result_hash'}})
 return body

def validate_task_artifact(artifact,state,task):
 model=_model_from_state_task(state,task)
 required={'schema_version':SCHEMA,'run_id':state['run_id'],'attempt_id':state['tasks'][task['task_identity']].get('attempt_id'),'research_freeze_identity':state['binding']['research_freeze_identity'],'research_plan_identity':state['binding']['research_plan_identity'],'manifest_identity':state['binding']['manifest_identity'],'task_identity':task['task_identity'],'model_id':task['model_id'],'symbol':task['symbol'],'parameter_grid_hash':model['parameter_grid_hash']}
 if any(artifact.get(key)!=value for key,value in required.items()): raise RecoverableExecutionError('task_artifact_provenance_mismatch')
 status=artifact.get('status');expected_train=model['grid_combinations'];expected_validation=min(state['binding']['top_k_train'],expected_train)
 if status=='COMPLETED':
  train=artifact.get('train_results');validation=artifact.get('validation_results')
  expected_train_ids,expected_top_ids,expected_validation_ids=_derive_completed_evidence(state,task,train,validation)
  if artifact.get('actual_train_evaluations')!=expected_train or artifact.get('expected_train_evaluations')!=expected_train or artifact.get('actual_validation_evaluations')!=expected_validation or artifact.get('expected_validation_evaluations')!=expected_validation or artifact.get('train_result_identities')!=expected_train_ids or artifact.get('selected_train_top_k')!=expected_top_ids or artifact.get('validation_result_identities')!=expected_validation_ids or artifact.get('error_type') or artifact.get('error_message'): raise RecoverableExecutionError('completed_task_result_incomplete')
 elif status=='FAILED':
  if not isinstance(artifact.get('error_type'),str) or not artifact['error_type'] or not isinstance(artifact.get('error_message'),str) or artifact.get('actual_train_evaluations') or artifact.get('actual_validation_evaluations') or artifact.get('train_results') or artifact.get('validation_results') or artifact.get('train_result_identities') or artifact.get('selected_train_top_k') or artifact.get('validation_result_identities'): raise RecoverableExecutionError('failed_task_result_invalid')
 else: raise RecoverableExecutionError('task_artifact_state_invalid')
 payload={key:value for key,value in artifact.items() if key not in {'started_at','ended_at','result_hash'}}
 if artifact.get('result_hash')!=_hash(payload): raise RecoverableExecutionError('task_result_hash_mismatch')
 return True

def _model_from_state_task(state,task):
 models=state['binding'].get('models')
 if not isinstance(models,list): raise RecoverableExecutionError('run_model_binding_missing')
 rows=[row for row in models if row.get('model_id')==task['model_id']]
 if len(rows)!=1: raise RecoverableExecutionError('task_model_not_frozen')
 return rows[0]
def _expected_train_ids(state,task):
 """Legacy helper: frozen parameter identities only, not completed result identities."""
 model=_model_from_state_task(state,task);grid=state['binding'].get('parameter_grids',{}).get(task['model_id'])
 if not isinstance(grid,dict) or not grid: raise RecoverableExecutionError('frozen_parameter_grid_missing')
 keys=sorted(grid);params=[dict(zip(keys,values)) for values in product(*(grid[key] for key in keys))]
 return [_hash({'task_identity':task['task_identity'],'parameter_grid_hash':model['parameter_grid_hash'],'params':row}) for row in params]
def complete_task(root,manifest,plan,artifact,*,authority=None):
 if not isinstance(authority,Mapping): raise RecoverableExecutionError('execution_authority_required')
 authorize_execution_context(manifest,n7=authority.get('n7'),n8=authority.get('n8'),repo_root=authority.get('repo_root'),requested_windows=authority.get('requested_windows'),output_path=authority.get('output_path'),requested_workers=authority.get('requested_workers'))
 with _run_lock(root): return _complete_task(root,manifest,plan,artifact)
def _complete_task(root,manifest,plan,artifact):
 state=_load_run_locked(root,manifest,plan);tasks=_validate_state(state,manifest,plan);task=tasks.get(artifact.get('task_identity'))
 if task is None: raise RecoverableExecutionError('unknown_task')
 if state['tasks'][task['task_identity']]['status']!='RUNNING': raise RecoverableExecutionError('task_not_running')
 validate_task_artifact(artifact,state,task)
 if artifact['status']!='COMPLETED': raise RecoverableExecutionError('complete_requires_completed_artifact')
 _write_new(_task_path(root,task['task_identity']),artifact);state['tasks'][task['task_identity']].update({'status':'COMPLETED','result_hash':artifact['result_hash'],'actual_train_evaluations':artifact['actual_train_evaluations'],'actual_validation_evaluations':artifact['actual_validation_evaluations'],'ended_at':time.time()});_refresh_accounting(state,plan);_bump(state);_replace(Path(root)/'run_state.json',state)
def fail_task(root,manifest,plan,task_identity,error_type,error_message,*,authority=None):
 if not isinstance(authority,Mapping): raise RecoverableExecutionError('execution_authority_required')
 authorize_execution_context(manifest,n7=authority.get('n7'),n8=authority.get('n8'),repo_root=authority.get('repo_root'),requested_windows=authority.get('requested_windows'),output_path=authority.get('output_path'),requested_workers=authority.get('requested_workers'))
 with _run_lock(root): return _fail_task(root,manifest,plan,task_identity,error_type,error_message)
def _fail_task(root,manifest,plan,task_identity,error_type,error_message):
 state=_load_run_locked(root,manifest,plan);tasks=_validate_state(state,manifest,plan)
 if task_identity not in tasks or state['tasks'][task_identity]['status']!='RUNNING': raise RecoverableExecutionError('task_not_running')
 artifact=task_result_payload(state,plan,task_identity,status='FAILED',error_type=error_type,error_message=error_message)
 validate_task_artifact(artifact,state,tasks[task_identity]);record=state['tasks'][task_identity];record.setdefault('attempts',[]).append({'attempt_id':record.get('attempt_id'),'status':'FAILED','owner':record.get('owner'),'error_type':error_type,'error_message':error_message,'ended_at':time.time()});record.update({'status':'FAILED','error_type':error_type,'error_message':error_message,'ended_at':time.time()});_refresh_accounting(state,plan);_bump(state);_replace(Path(root)/'run_state.json',state)
def final_result_identity(root,manifest,plan):
 state=load_run(root,manifest,plan)
 if any(record['status']!='COMPLETED' for record in state['tasks'].values()): raise RecoverableExecutionError('partial_run_cannot_finalize')
 rows=[_read(_task_path(root,key)) for key in sorted(state['tasks'])]
 return _hash({'run_id':state['run_id'],'task_result_hashes':[(row['task_identity'],row['result_hash']) for row in rows]})
