"""N7 production-shaped, non-OOS formal execution orchestration.

This module never discovers data paths or invokes a loader at import/preflight
time.  A future authorized caller must inject a boundary-aware window loader.
That loader is called only after the accepted N3/N5/N6 chain is verified.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .candidate_universe import CURRENT_PROTOCOL_SCOPE
from .plan_executor import (
    PlanExecutionError, execute_verified_plan, load_verified_plan, make_canonical_evaluator,
    validate_execution_outputs,
)


class N7ExecutionError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class N7Context:
    plan: Mapping[str, Any]
    freeze: Mapping[str, Any]
    entries: tuple
    boundary_lock: Mapping[str, Any]


def load_n7_context(plan_path, freeze_path, boundary_lock: Mapping[str, Any]) -> N7Context:
    """Complete metadata-only N3 -> N5 -> N6 verification before data access."""
    plan, entries=load_verified_plan(plan_path,freeze_path,boundary_lock)
    freeze=json.loads(Path(freeze_path).read_text(encoding='utf-8'))
    if CURRENT_PROTOCOL_SCOPE.engine_identity!='quantbot.backtest.engine_v2.BacktestEngine':
        raise N7ExecutionError('canonical_engine_identity_mismatch')
    if CURRENT_PROTOCOL_SCOPE.cost_model_identity!='quantbot.backtest.costs.CostModel':
        raise N7ExecutionError('canonical_cost_model_identity_mismatch')
    if plan['research_freeze_identity']!=freeze['research_freeze_identity']:
        raise N7ExecutionError('research_freeze_identity_mismatch')
    return N7Context(plan=plan,freeze=freeze,entries=tuple(entries),boundary_lock=boundary_lock)


def authorize_n7_window(window: str) -> str:
    if window not in {'TRAIN','VALIDATION'}:
        raise N7ExecutionError('n7_window_not_authorized')
    return window


def verify_n7_runtime(engine_identity: str, cost_model_identity: str) -> None:
    if engine_identity!=CURRENT_PROTOCOL_SCOPE.engine_identity:
        raise N7ExecutionError('n7_engine_identity_mismatch')
    if cost_model_identity!=CURRENT_PROTOCOL_SCOPE.cost_model_identity:
        raise N7ExecutionError('n7_cost_model_identity_mismatch')


def make_n7_window_loader(context: N7Context, window_loader: Callable[..., Any]):
    """Guard an injected canonical boundary-aware loader against OOS access."""
    def guarded(*, window: str, symbol: str, task: Mapping[str, Any]):
        authorize_n7_window(window)
        if task.get('symbol')!=symbol:
            raise N7ExecutionError('task_symbol_mismatch')
        return window_loader(window=window,symbol=symbol,task=task,boundary=context.plan['boundary'])
    return guarded


def make_n7_canonical_evaluator(context: N7Context, window_loader, strategy_resolver, engine_factory):
    """Bind the N7 window guard to the accepted BacktestEngine/CostModel adapter."""
    guarded=make_n7_window_loader(context,window_loader)
    return make_canonical_evaluator(
        lambda *,window,entry,task: guarded(window=window,symbol=task['symbol'],task=task),
        strategy_resolver,
        engine_factory,
    )


def _runtime_provenance(context: N7Context, task: Mapping[str, Any]) -> dict[str, Any]:
    model=next(item for item in context.plan['models'] if item['model_id']==task['model_id'])
    return {
        'research_freeze_identity':context.plan['research_freeze_identity'],
        'research_plan_identity':context.plan['research_plan_identity'],
        'task_identity':task['task_identity'],'model_id':task['model_id'],'symbol':task['symbol'],
        'parameter_grid_hash':model['parameter_grid_hash'],
        'strategy_function_hash':model['strategy_function_hash'],
        'implementation_module_hash':model['implementation_module_hash'],
        'engine_identity':CURRENT_PROTOCOL_SCOPE.engine_identity,
        'cost_model_identity':CURRENT_PROTOCOL_SCOPE.cost_model_identity,
        'boundary_identity_hash':context.plan['boundary_identity_hash'],
        'dataset_id':context.plan['boundary']['dataset_id'],
    }


def run_n7_plan(context: N7Context, evaluator: Callable[..., Mapping[str, Any]], *,
                engine_identity: str = CURRENT_PROTOCOL_SCOPE.engine_identity,
                cost_model_identity: str = CURRENT_PROTOCOL_SCOPE.cost_model_identity):
    """Execute exactly the frozen plan through the accepted N6 executor.

    This function is intentionally not invoked by the N7 preflight command.
    """
    verify_n7_runtime(engine_identity,cost_model_identity)
    outputs=execute_verified_plan(context.plan,context.entries,evaluator,context.freeze)
    validate_execution_outputs(context.plan,outputs,context.entries)
    result=[]
    by_task={task['task_identity']:task for task in context.plan['tasks']}
    for output in outputs:
        row=dict(output)
        row.update(_runtime_provenance(context,by_task[output['task_identity']]))
        result.append(row)
    return result


def build_n7_result(context: N7Context, outputs: list[Mapping[str, Any]]) -> dict[str, Any]:
    validate_execution_outputs(context.plan,outputs,context.entries)
    by_task={task['task_identity']:task for task in context.plan['tasks']}
    enriched=[]
    for output in outputs:
        row=dict(output);row.update(_runtime_provenance(context,by_task[row['task_identity']]))
        if row['status']=='COMPLETED':
            row['train']=[{**item,'window':'TRAIN'} for item in row['train']]
            row['validation']=[{**item,'window':'VALIDATION'} for item in row['validation']]
        enriched.append(row)
    expected=len(context.plan['tasks']); completed=sum(row['status']=='COMPLETED' for row in enriched)
    payload={
        'schema_version':'quantbot-n7-result-v1',
        'research_freeze_identity':context.plan['research_freeze_identity'],
        'research_plan_identity':context.plan['research_plan_identity'],
        'candidate_universe_hash':context.plan['candidate_universe_hash'],
        'protocol_scope_hash':context.plan['protocol_scope_hash'],
        'boundary_identity_hash':context.plan['boundary_identity_hash'],
        'dataset_id':context.plan['boundary']['dataset_id'],
        'engine_identity':CURRENT_PROTOCOL_SCOPE.engine_identity,
        'cost_model_identity':CURRENT_PROTOCOL_SCOPE.cost_model_identity,
        'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED',
        'expected_tasks':expected,'completed_tasks':completed,'failed_tasks':expected-completed,
        'run_status':'COMPLETE' if completed==expected else 'PARTIAL',
        'outputs':enriched,
    }
    payload['result_identity']=_hash(payload)
    return payload


def validate_n7_result(context: N7Context, result: Mapping[str, Any]) -> bool:
    if result.get('schema_version')!='quantbot-n7-result-v1': raise N7ExecutionError('result_schema_invalid')
    for key in ('research_freeze_identity','research_plan_identity','candidate_universe_hash','protocol_scope_hash','boundary_identity_hash'):
        if result.get(key)!=context.plan.get(key): raise N7ExecutionError('result_provenance_mismatch')
    if result.get('dataset_id')!=context.plan['boundary']['dataset_id']: raise N7ExecutionError('result_dataset_mismatch')
    if result.get('engine_identity')!=CURRENT_PROTOCOL_SCOPE.engine_identity or result.get('cost_model_identity')!=CURRENT_PROTOCOL_SCOPE.cost_model_identity:
        raise N7ExecutionError('result_runtime_identity_mismatch')
    if result.get('oos_status')!='SEALED' or result.get('oos_authorization')!='NOT_AUTHORIZED': raise N7ExecutionError('result_oos_violation')
    validate_execution_outputs(context.plan,result.get('outputs'),context.entries)
    by_task={task['task_identity']:task for task in context.plan['tasks']}
    for row in result['outputs']:
        for key,value in _runtime_provenance(context,by_task[row['task_identity']]).items():
            if row.get(key)!=value: raise N7ExecutionError('result_task_provenance_mismatch')
        if row['status']=='COMPLETED':
            if any(item.get('window')!='TRAIN' for item in row['train']) or any(item.get('window')!='VALIDATION' for item in row['validation']):
                raise N7ExecutionError('result_window_provenance_mismatch')
    total=len(context.plan['tasks']); completed=sum(row['status']=='COMPLETED' for row in result['outputs'])
    if result.get('expected_tasks')!=total or result.get('completed_tasks')!=completed or result.get('failed_tasks')!=total-completed:
        raise N7ExecutionError('result_count_mismatch')
    if result.get('run_status')!=('COMPLETE' if completed==total else 'PARTIAL'):
        raise N7ExecutionError('result_status_mismatch')
    identity=dict(result); claimed=identity.pop('result_identity',None)
    if claimed!=_hash(identity): raise N7ExecutionError('result_identity_mismatch')
    return True


def write_n7_result(output_dir, result: Mapping[str, Any]) -> Path:
    """Write a new identity-named artifact once; never overwrite frozen artifacts."""
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    path=root/f"N7_FORMAL_RESULT_{result['result_identity']}.json"
    with path.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,ensure_ascii=False,sort_keys=True,indent=2)
        handle.write('\n')
    return path
