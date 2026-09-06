"""Synthetic-only N4 drift and pre-read OOS blocking tests."""
from pathlib import Path
from dataclasses import replace
import json, sys, tempfile
from types import SimpleNamespace
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.authorization_gate import FreezeAuthorizationError, require_oos_authorized, validate_pre_research_freeze
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from quantbot.research.freeze_manifest import build_freeze_manifest
from quantbot.research.model_registry import _REGISTRY, list_models, register_existing_models, validate_registry
from quantbot.strategies.model_pool import register_model_pool
LOCK={"dataset_id":"T","market":"um","interval":"1h","requested_end":"r","actual_end":"a","status":"LOCKED","splits":[{"name":"TRAIN","start":"1","end":"2"},{"name":"VALIDATION","start":"3","end":"4"},{"name":"OOS","start":"5","end":"6"}],"policies":{"gap_policy":"non_tradable","synthetic_candles":False,"lookahead_policy":"strictly_before"}}
def fail(fn,reason):
 try: fn()
 except FreezeAuthorizationError as e: assert reason in e.reasons; return
 raise AssertionError(reason)
def main():
 register_existing_models();register_model_pool(); models=build_candidate_universe(); m=build_freeze_manifest(models,CURRENT_PROTOCOL_SCOPE,LOCK,"base")
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/"freeze.json";p.write_text(json.dumps(m));assert validate_pre_research_freeze(p,LOCK,models)=={"research_freeze_identity":m["research_freeze_identity"],"oos_authorized":False}
  before=list_models(); validate_pre_research_freeze(p,LOCK); validate_pre_research_freeze(p,LOCK); assert list_models()==before
  fail(lambda:require_oos_authorized(p,LOCK,models),"oos_not_authorized")
  changed=list(models);changed.pop();fail(lambda:validate_pre_research_freeze(p,LOCK,changed),"model_count_mismatch")
  fail(lambda:validate_pre_research_freeze(Path(td)/"none",LOCK,models),"missing_freeze_manifest")
  bad=dict(m);bad["schema_version"]="bad";p.write_text(json.dumps(bad));fail(lambda:validate_pre_research_freeze(p,LOCK,models),"unsupported_freeze_schema")
  p.write_text(json.dumps(m))
  # Each candidate semantic mutation is independently exercised.
  for field,value in (("parameter_grid_hash","p"*64),("secondary_traits",("ema",)),("implementation_module_hash","i"*64)):
   changed=list(models);changed[0]=replace(changed[0],**{field:value});fail(lambda c=changed:validate_pre_research_freeze(p,LOCK,c),"candidate_universe_hash_mismatch")
  changed=list(models);changed.pop();fail(lambda:validate_pre_research_freeze(p,LOCK,changed),"candidate_universe_hash_mismatch")
  changed=list(models)+[models[0]];fail(lambda:validate_pre_research_freeze(p,LOCK,changed),"candidate_universe_hash_mismatch")
  for field,value in (("symbols",("X",)),("timeframe","4h"),("engine_identity","bad"),("cost_model_identity","bad"),("causal_execution_policy","bad")):
   fail(lambda f=field,v=value:validate_pre_research_freeze(p,LOCK,models,replace(CURRENT_PROTOCOL_SCOPE,**{f:v})),"protocol_scope_hash_mismatch")
  for mut in (("actual_end","z"),("splits",[{"name":"TRAIN","start":"z","end":"2"},*LOCK["splits"][1:]]),("splits",[LOCK["splits"][0],{"name":"VALIDATION","start":"z","end":"4"},LOCK["splits"][2]]),("splits",[LOCK["splits"][0],LOCK["splits"][1],{"name":"OOS","start":"z","end":"6"}])):
   lock=dict(LOCK);lock[mut[0]]=mut[1];fail(lambda l=lock:validate_pre_research_freeze(p,l,models),"boundary_identity_hash_mismatch")
  for key,value,reason in (("oos_status","OPEN","oos_not_sealed"),("oos_authorization","AUTHORIZED","oos_authorization_changed")):
   bad=json.loads(json.dumps(m));bad["freeze_status"][key]=value;p.write_text(json.dumps(bad));fail(lambda:validate_pre_research_freeze(p,LOCK,models),reason)
  p.write_text(json.dumps(m))
  # Empty caller registry stays empty; the normal non-idempotent registration path then succeeds.
  original=dict(_REGISTRY)
  try:
   _REGISTRY.clear();assert not list_models();validate_pre_research_freeze(p,LOCK);assert not list_models()
   register_existing_models();register_model_pool();validate_registry();assert len(list_models())==36
  finally:
   _REGISTRY.clear();_REGISTRY.update(original)
  # Actual D2 guarded run: every pre-research reader must remain untouched.
  import scripts.run_phase2_3_5_d2_oos_validation as d2
  d2.build_research_dataset=Mock(); d2._load_freeze=Mock(); d2.load_research_frames=Mock()
  fail(lambda:d2.run(SimpleNamespace(lock=str(ROOT/"data/reports/research_boundary_lock.json"),freeze_manifest="x",raw_root="x",parquet_root="x",workers=1)),"oos_not_authorized")
  assert d2.build_research_dataset.call_count==d2._load_freeze.call_count==d2.load_research_frames.call_count==0
  # Actual D3 guarded run: no D1/D2/curve reader can run after the gate rejects.
  import scripts.run_phase2_3_5_d3_oos_analysis as d3
  d3.load_json=Mock(); d3.load_curves=Mock()
  fail(lambda:d3.run(SimpleNamespace(d1="x",d2="x",curves="x",output="x")),"oos_not_authorized")
  assert d3.load_json.call_count==d3.load_curves.call_count==0
 print("RESEARCH_AUTHORIZATION_GATE_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
