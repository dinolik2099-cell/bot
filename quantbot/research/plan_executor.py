"""N6 injectable, non-OOS executor; formal runs are intentionally not invoked here."""
from __future__ import annotations
import json
import math
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

def preflight_summary(plan_path, freeze_path, boundary_lock):
    """Verify the committed N3/N5 chain without constructing a data interface."""
    plan, entries=load_verified_plan(plan_path,freeze_path,boundary_lock)
    return {
        'research_plan_identity':plan['research_plan_identity'],
        'research_freeze_identity':plan['research_freeze_identity'],
        'models':len(entries),
        'tasks':len(plan['tasks']),
        'oos_status':plan['oos_status'],
        'oos_authorization':plan['oos_authorization'],
    }

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

def validate_metrics(metrics):
    required=('total_return','max_drawdown','profit_factor','trades')
    if not isinstance(metrics,dict) or any(key not in metrics for key in required): raise PlanExecutionError('invalid_evaluator_metrics')
    if (not all(math.isfinite(float(metrics[key])) for key in ('total_return','max_drawdown'))
            or math.isnan(float(metrics['profit_factor'])) or float(metrics['profit_factor'])<0
            or int(metrics['trades'])<0): raise PlanExecutionError('invalid_evaluator_metrics')
    return metrics

def make_canonical_evaluator(frame_loader, strategy_resolver, engine_factory):
    """Return an injectable evaluator bound to the accepted engine/cost classes.

    The loader is intentionally supplied by the future authorized runner.  This
    layer neither discovers files nor opens market data by itself.
    """
    from quantbot.backtest.costs import CostModel
    from quantbot.backtest.engine_v2 import BacktestEngine
    from quantbot.research.evaluation import evaluate_strategy
    def evaluator(window, entry, task, params):
        authorize_window({},window)
        engine=engine_factory()
        if not isinstance(engine,BacktestEngine) or not isinstance(engine.cost_model,CostModel):
            raise PlanExecutionError('canonical_engine_or_cost_model_required')
        frame=frame_loader(window=window,entry=entry,task=task)
        strategy=strategy_resolver(entry.model_id)
        result=evaluate_strategy(symbol=task['symbol'],window=window,frame=frame,strategy=strategy,engine=engine,params=params,tag=task['task_identity'])
        metrics=result.backtest.metrics()
        return {key:metrics[key] for key in ('total_return','max_drawdown','profit_factor','trades')}
    return evaluator

def execute_synthetic_cell(entry, task, evaluator, top_k=5):
    """Injected evaluator only; caller is responsible for verified data access."""
    train=[]
    for params in frozen_grid(entry):
        metrics=validate_metrics(evaluator('TRAIN', entry, task, params))
        train.append({"params":params,**metrics})
    top=rank_train(train)[:top_k]
    validation=[]
    for row in top:
        metrics=validate_metrics(evaluator('VALIDATION', entry, task, row['params']))
        retained=metrics['total_return']>0 and metrics['profit_factor']>=1.0
        validation.append({"params":row['params'],**metrics,"research_state":"RETAINED_FOR_FUTURE_REVIEW" if retained else "HOLD","oos_authorized":False})
    return {"task_identity":task['task_identity'],"model_id":task['model_id'],"symbol":task['symbol'],"train":train,"validation":validation}

def execute_verified_plan(plan, entries, evaluator, accepted_freeze_manifest):
    """Execute only a plan revalidated against the accepted freeze chain.

    ``evaluator`` is deliberately injected.  Validation therefore happens before
    the first possible evaluator (and, by extension, market-data) call.
    """
    validate_plan(plan, entries, accepted_freeze_manifest)
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
    validate_execution_outputs(plan,outputs,entries)
    return outputs

def execution_audit(plan, outputs, expected_entries):
    """Produce accounting only after freeze-bound output validation succeeds."""
    validate_execution_outputs(plan,outputs,expected_entries)
    completed=sum(row.get('status')=='COMPLETED' for row in outputs)
    return {'research_plan_identity':plan['research_plan_identity'],'research_freeze_identity':plan['research_freeze_identity'],
            'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','tasks_total':len(outputs),
            'tasks_completed':completed,'tasks_failed':len(outputs)-completed,
            'train_evaluations':sum(len(row.get('train',[])) for row in outputs),
            'validation_evaluations':sum(len(row.get('validation',[])) for row in outputs)}

def _params_key(params):
    if not isinstance(params,dict): raise PlanExecutionError('output_params_invalid')
    return json.dumps(params,sort_keys=True,separators=(',',':'))

def validate_execution_outputs(plan, outputs, expected_entries):
    """Fail closed unless every output is a complete frozen-plan cell.

    ``expected_entries`` is the independently reconstructed accepted candidate
    universe.  The plan's own model rows are evidence, not the authority for a
    parameter grid.
    """
    if not isinstance(outputs,list): raise PlanExecutionError('output_list_required')
    expected={task['task_identity']:task for task in plan['tasks']}
    plan_models={model['model_id']:model for model in plan['models']}
    entries={entry.model_id:entry for entry in expected_entries}
    if set(entries)!=set(plan_models): raise PlanExecutionError('output_entry_set_mismatch')
    actual_ids=[row.get('task_identity') for row in outputs]
    if len(actual_ids)!=len(expected) or set(actual_ids)!=set(expected) or len(set(actual_ids))!=len(actual_ids):
        raise PlanExecutionError('output_task_set_mismatch')
    for row in outputs:
        task=expected.get(row.get('task_identity'))
        if task is None or row.get('model_id')!=task['model_id'] or row.get('symbol')!=task['symbol']: raise PlanExecutionError('output_task_provenance_mismatch')
        if row.get('research_plan_identity')!=plan['research_plan_identity'] or row.get('research_freeze_identity')!=plan['research_freeze_identity']: raise PlanExecutionError('output_freeze_provenance_mismatch')
        entry=entries[task['model_id']]; model=plan_models[task['model_id']]
        if row.get('parameter_grid_hash')!=model.get('parameter_grid_hash') or row.get('parameter_grid_hash')!=entry.parameter_grid_hash:
            raise PlanExecutionError('output_parameter_grid_hash_mismatch')
        status=row.get('status')
        if status not in {'COMPLETED','FAILED'}: raise PlanExecutionError('output_status_invalid')
        if status=='FAILED':
            if not isinstance(row.get('error_type'),str) or not row['error_type']: raise PlanExecutionError('failed_error_type_required')
            if 'error_message' not in row or not isinstance(row['error_message'],str): raise PlanExecutionError('failed_error_message_required')
            if 'train' in row or 'validation' in row: raise PlanExecutionError('failed_output_contains_results')
            continue
        if row.get('error_type') or row.get('error_message'): raise PlanExecutionError('completed_output_contains_error')
        train=row.get('train'); validation=row.get('validation')
        if not isinstance(train,list) or not isinstance(validation,list): raise PlanExecutionError('completed_output_results_required')
        grid=frozen_grid(entry); grid_keys={_params_key(params) for params in grid}
        train_keys=[_params_key(item.get('params')) if isinstance(item,dict) else None for item in train]
        if len(train)!=model.get('grid_combinations') or len(train)!=len(grid) or len(set(train_keys))!=len(train) or set(train_keys)!=grid_keys:
            raise PlanExecutionError('completed_train_grid_mismatch')
        for item in train: validate_metrics(item)
        expected_top=rank_train(train)[:min(plan['top_k_train'],len(grid))]
        expected_top_keys={_params_key(item['params']) for item in expected_top}
        validation_keys=[_params_key(item.get('params')) if isinstance(item,dict) else None for item in validation]
        if len(validation)!=len(expected_top) or len(set(validation_keys))!=len(validation) or set(validation_keys)!=expected_top_keys:
            raise PlanExecutionError('completed_validation_top_k_mismatch')
        for item in validation:
            validate_metrics(item)
            if item.get('oos_authorized') is not False: raise PlanExecutionError('output_oos_authorization_violation')
    return True
