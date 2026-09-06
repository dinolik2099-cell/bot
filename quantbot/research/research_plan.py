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
def task_id(freeze,model_id,symbol,grid_hash,protocol_hash): return _hash({"freeze":freeze,"model_id":model_id,"symbol":symbol,"grid":grid_hash,"protocol_scope_hash":protocol_hash,"schema":SCHEMA_VERSION})
def identity_payload(plan): return {k:plan[k] for k in ("schema_version","research_freeze_identity","candidate_universe_hash","protocol_scope","protocol_scope_hash","boundary","boundary_identity_hash","models","symbols","ranking","top_k_train","viability","oos_status","oos_authorization","tasks","counts")}
def build_plan(entries,scope,lock,freeze):
 symbols=list(scope.symbols); models=list(sorted(entries,key=lambda x:x.model_id)); boundary=boundary_identity(lock)
 rows=[{"model_id":e.model_id,"family":e.family,"secondary_traits":list(e.secondary_traits),"warmup_bars":e.warmup_bars,"required_features":list(e.required_features),"parameter_grid_hash":e.parameter_grid_hash,"strategy_function_hash":e.strategy_function_hash,"implementation_module_hash":e.implementation_module_hash,"grid_combinations":grid_count(e)} for e in models]
 protocol_hash=_hash(protocol_scope_dict(scope));tasks=[{"model_id":e.model_id,"symbol":s,"task_identity":task_id(freeze,e.model_id,s,e.parameter_grid_hash,protocol_hash)} for e in models for s in symbols]
 core={"schema_version":SCHEMA_VERSION,"research_freeze_identity":freeze,"candidate_universe_hash":_hash([e.canonical_dict() for e in models]),"protocol_scope":protocol_scope_dict(scope),"protocol_scope_hash":protocol_hash,"boundary":boundary,"boundary_identity_hash":_hash(boundary),"models":rows,"symbols":symbols,"ranking":RANKING,"top_k_train":TOP_K_TRAIN,"viability":VIABILITY,"oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED","tasks":tasks,"counts":{"models":len(models),"symbols":len(symbols),"model_symbol_cells":len(tasks),"train_evaluations":sum(x["grid_combinations"] for x in rows)*len(symbols),"validation_evaluations_max":len(tasks)*TOP_K_TRAIN}}
 core["research_plan_identity"]=_hash(identity_payload(core));return core
def validate_plan(plan):
 if plan.get("schema_version")!=SCHEMA_VERSION: raise ValueError("unsupported_plan_schema")
 if plan.get("oos_status")!="SEALED" or plan.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("oos_not_authorized")
 if plan.get("protocol_scope_hash")!=_hash(plan.get("protocol_scope")): raise ValueError("protocol_scope_hash_mismatch")
 if plan.get("boundary_identity_hash")!=_hash(plan.get("boundary")): raise ValueError("boundary_identity_hash_mismatch")
 counts=plan.get("counts",{});models=plan.get("models",[]);tasks=plan.get("tasks",[])
 if not plan.get("research_freeze_identity") or not plan.get("candidate_universe_hash"): raise ValueError("missing_freeze_chain")
 if counts.get("models")!=len(models) or counts.get("symbols")!=len(plan.get("symbols",[])): raise ValueError("count_mismatch")
 if counts.get("model_symbol_cells")!=len(tasks): raise ValueError("task_count_mismatch")
 if len({(x.get("model_id"),x.get("symbol")) for x in tasks})!=len(tasks) or len({x.get("task_identity") for x in tasks})!=len(tasks): raise ValueError("task_identity_mismatch")
 if counts.get("train_evaluations")!=sum(x.get("grid_combinations",0) for x in models)*counts.get("symbols"): raise ValueError("train_evaluations_mismatch")
 if counts.get("validation_evaluations_max")!=counts.get("model_symbol_cells")*plan.get("top_k_train"): raise ValueError("validation_evaluations_mismatch")
 if plan.get("research_plan_identity")!=_hash(identity_payload(plan)): raise ValueError("research_plan_identity_mismatch")
 return True
