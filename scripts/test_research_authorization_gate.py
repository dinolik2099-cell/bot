"""Synthetic-only N4 drift and pre-read OOS blocking tests."""
from pathlib import Path
from dataclasses import replace
import json, sys, tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.authorization_gate import FreezeAuthorizationError, require_oos_authorized, validate_pre_research_freeze
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from quantbot.research.freeze_manifest import build_freeze_manifest
from quantbot.research.model_registry import register_existing_models
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
  fail(lambda:require_oos_authorized(p,LOCK,models),"oos_not_authorized")
  changed=list(models);changed.pop();fail(lambda:validate_pre_research_freeze(p,LOCK,changed),"model_count_mismatch")
  fail(lambda:validate_pre_research_freeze(Path(td)/"none",LOCK,models),"missing_freeze_manifest")
  bad=dict(m);bad["schema_version"]="bad";p.write_text(json.dumps(bad));fail(lambda:validate_pre_research_freeze(p,LOCK,models),"unsupported_freeze_schema")
 print("RESEARCH_AUTHORIZATION_GATE_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
