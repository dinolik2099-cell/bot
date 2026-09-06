"""N6 injectable, non-OOS executor; formal runs are intentionally not invoked here."""
from __future__ import annotations
import json
from pathlib import Path
from itertools import product
from .research_plan import validate_plan, task_id
from .authorization_gate import validate_pre_research_freeze
from .candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from .model_registry import register_existing_models

class PlanExecutionError(RuntimeError): pass

def load_verified_plan(plan_path, freeze_path, boundary_lock):
    """Validate all identities before a caller may access its data interface."""
    plan=json.loads(Path(plan_path).read_text(encoding='utf-8'))
    freeze=json.loads(Path(freeze_path).read_text(encoding='utf-8'))
    from quantbot.research.model_registry import _REGISTRY
    from quantbot.strategies.model_pool import register_model_pool
    snapshot=dict(_REGISTRY)
    try:
        _REGISTRY.clear();register_existing_models();register_model_pool();entries=build_candidate_universe()
    finally:
        _REGISTRY.clear();_REGISTRY.update(snapshot)
    validate_pre_research_freeze(freeze_path,boundary_lock,models=entries,scope=CURRENT_PROTOCOL_SCOPE)
    validate_plan(plan,entries,freeze)
    if plan.get('oos_status')!='SEALED' or plan.get('oos_authorization')!='NOT_AUTHORIZED': raise PlanExecutionError('oos_not_sealed')
    return plan,entries

def authorize_window(plan, window):
    if window not in {'TRAIN','VALIDATION'}: raise PlanExecutionError('window_not_authorized')
    return window

def load_task_frame(plan, task_identity, window, data_loader):
    """Only call the injected loader after plan/task/window authorization."""
    authorize_window(plan, window)
    matches=[task for task in plan.get('tasks',[]) if task.get('task_identity')==task_identity]
    if len(matches)!=1: raise PlanExecutionError('unknown_or_duplicate_task')
    task=matches[0]
    model=next((row for row in plan.get('models',[]) if row.get('model_id')==task['model_id']),None)
    if model is None: raise PlanExecutionError('task_model_missing')
    expected=task_id(plan['research_freeze_identity'],task['model_id'],task['symbol'],model['parameter_grid_hash'],plan['protocol_scope_hash'])
    if task_identity!=expected: raise PlanExecutionError('task_identity_mismatch')
    return data_loader(symbol=task['symbol'], window=window, task=task)

def rank_train(rows):
    return sorted(rows,key=lambda r:(-(r['total_return']-r['max_drawdown']),-r['profit_factor'],r['max_drawdown'],-r['trades'],json.dumps(r['params'],sort_keys=True)))

def frozen_grid(entry):
    keys=sorted(entry.parameter_grid)
    return [dict(zip(keys, values)) for values in product(*(entry.parameter_grid[k] for k in keys))]

def execute_synthetic_cell(entry, task, evaluator, top_k=5):
    """Injected evaluator only; caller is responsible for verified data access."""
    train=[]
    for params in frozen_grid(entry):
        metrics=evaluator('TRAIN', entry, task, params)
        train.append({"params":params,**metrics})
    top=rank_train(train)[:top_k]
    validation=[]
    for row in top:
        metrics=evaluator('VALIDATION', entry, task, row['params'])
        retained=metrics['total_return']>0 and metrics['profit_factor']>=1.0
        validation.append({"params":row['params'],**metrics,"research_state":"RETAINED_FOR_FUTURE_REVIEW" if retained else "HOLD","oos_authorized":False})
    return {"task_identity":task['task_identity'],"model_id":task['model_id'],"symbol":task['symbol'],"train":train,"validation":validation}

def execute_verified_plan(plan, entries, evaluator):
    """Pure plan orchestration; evaluator remains injected and data-free here."""
    if plan.get('oos_status')!='SEALED' or plan.get('oos_authorization')!='NOT_AUTHORIZED': raise PlanExecutionError('oos_not_sealed')
    by_id={entry.model_id:entry for entry in entries}
    if set(by_id)!={row['model_id'] for row in plan['models']}: raise PlanExecutionError('entry_set_mismatch')
    outputs=[]
    for task in sorted(plan['tasks'],key=lambda x:x['task_identity']):
        entry=by_id.get(task['model_id'])
        if entry is None: raise PlanExecutionError('task_model_missing')
        provenance={'research_plan_identity':plan['research_plan_identity'],'research_freeze_identity':plan['research_freeze_identity'],'parameter_grid_hash':entry.parameter_grid_hash}
        try:
            cell=execute_synthetic_cell(entry,task,evaluator,top_k=plan['top_k_train'])
            cell.update(provenance);cell['status']='COMPLETED'
        except Exception as exc:
            cell={'task_identity':task['task_identity'],'model_id':task['model_id'],'symbol':task['symbol'],**provenance,'status':'FAILED','error_type':type(exc).__name__,'error_message':str(exc)}
        outputs.append(cell)
    return outputs

def execution_audit(plan, outputs):
    """Deterministic, result-free execution accounting for audit transport."""
    completed=sum(row.get('status')=='COMPLETED' for row in outputs)
    return {'research_plan_identity':plan['research_plan_identity'],'research_freeze_identity':plan['research_freeze_identity'],
            'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','tasks_total':len(outputs),
            'tasks_completed':completed,'tasks_failed':len(outputs)-completed,
            'train_evaluations':sum(len(row.get('train',[])) for row in outputs),
            'validation_evaluations':sum(len(row.get('validation',[])) for row in outputs)}
