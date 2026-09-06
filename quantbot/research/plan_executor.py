"""N6 injectable, non-OOS executor; formal runs are intentionally not invoked here."""
from __future__ import annotations
import json
from pathlib import Path
from .research_plan import validate_plan
from .authorization_gate import validate_pre_research_freeze
from .candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from .model_registry import register_existing_models

class PlanExecutionError(RuntimeError): pass

def load_verified_plan(plan_path, freeze_path, boundary_lock):
    """Validate all identities before a caller may access its data interface."""
    plan=json.loads(Path(plan_path).read_text(encoding='utf-8'))
    freeze=json.loads(Path(freeze_path).read_text(encoding='utf-8'))
    from quantbot.strategies.model_pool import register_model_pool
    register_existing_models();register_model_pool();entries=build_candidate_universe()
    validate_pre_research_freeze(freeze_path,boundary_lock,models=entries,scope=CURRENT_PROTOCOL_SCOPE)
    validate_plan(plan,entries,freeze)
    if plan.get('oos_status')!='SEALED' or plan.get('oos_authorization')!='NOT_AUTHORIZED': raise PlanExecutionError('oos_not_sealed')
    return plan,entries

def authorize_window(plan, window):
    if window not in {'TRAIN','VALIDATION'}: raise PlanExecutionError('window_not_authorized')
    return window

def rank_train(rows):
    return sorted(rows,key=lambda r:(-(r['total_return']-r['max_drawdown']),-r['profit_factor'],r['max_drawdown'],-r['trades'],json.dumps(r['params'],sort_keys=True)))
