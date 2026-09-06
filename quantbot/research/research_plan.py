"""Metadata-only, freeze-bound non-OOS research execution plans."""
from __future__ import annotations
import hashlib, json
from itertools import product
from .freeze_manifest import boundary_identity, protocol_scope_dict, _hash

SCHEMA_VERSION="quantbot-research-plan-n5-v1"; TOP_K_TRAIN=5
RANKING={"primary":"total_return_minus_max_drawdown","tie_breakers":["profit_factor_desc","max_drawdown_asc","trades_desc","parameter_serialization_asc"]}
VIABILITY={"validation_total_return":"gt_0","validation_profit_factor":"gte_1.0","retained_state":"RETAINED_FOR_FUTURE_REVIEW","otherwise":"HOLD","oos_authorization":"NOT_AUTHORIZED"}
def grid_count(entry):
 n=1
 for values in entry.parameter_grid.values(): n*=len(values)
 return n
def task_id(freeze,entry,symbol): return _hash({"freeze":freeze,"model_id":entry.model_id,"symbol":symbol,"grid":entry.parameter_grid_hash,"timeframe":"1h","protocol":SCHEMA_VERSION})
def build_plan(entries,scope,lock,freeze):
 symbols=list(scope.symbols); models=list(sorted(entries,key=lambda x:x.model_id)); boundary=boundary_identity(lock)
 rows=[{"model_id":e.model_id,"family":e.family,"secondary_traits":list(e.secondary_traits),"warmup_bars":e.warmup_bars,"required_features":list(e.required_features),"parameter_grid_hash":e.parameter_grid_hash,"strategy_function_hash":e.strategy_function_hash,"implementation_module_hash":e.implementation_module_hash,"grid_combinations":grid_count(e)} for e in models]
 tasks=[{"model_id":e.model_id,"symbol":s,"task_identity":task_id(freeze,e,s)} for e in models for s in symbols]
 core={"research_freeze_identity":freeze,"candidate_universe_hash":_hash([e.canonical_dict() for e in models]),"protocol_scope":protocol_scope_dict(scope),"boundary":boundary,"models":rows,"symbols":symbols,"ranking":RANKING,"top_k_train":TOP_K_TRAIN,"viability":VIABILITY,"oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"}
 core["research_plan_identity"]=_hash(core);core.update({"schema_version":SCHEMA_VERSION,"tasks":tasks,"counts":{"models":len(models),"symbols":len(symbols),"model_symbol_cells":len(tasks),"train_evaluations":sum(x["grid_combinations"] for x in rows)*len(symbols),"validation_evaluations_max":len(tasks)*TOP_K_TRAIN}});return core
