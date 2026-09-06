"""Synthetic N3 freeze identity contracts; no boundary file or OOS result access."""
from dataclasses import replace
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from quantbot.research.freeze_manifest import build_freeze_manifest
from quantbot.research.model_registry import register_existing_models
from quantbot.strategies.model_pool import register_model_pool

LOCK={"dataset_id":"TEST","market":"um","interval":"1h","requested_end":"2026-08","actual_end":"2026-07","status":"LOCKED","splits":[{"name":"TRAIN","start":"a","end":"b"},{"name":"VALIDATION","start":"c","end":"d"},{"name":"OOS","start":"e","end":"f"}],"policies":{"gap_policy":"non_tradable","synthetic_candles":False,"lookahead_policy":"strictly_before"}}
def main():
 register_existing_models();register_model_pool(); entries=build_candidate_universe()
 a=build_freeze_manifest(entries,CURRENT_PROTOCOL_SCOPE,LOCK,"abc",created_at="one");b=build_freeze_manifest(entries,CURRENT_PROTOCOL_SCOPE,LOCK,"abc",created_at="two")
 assert a["research_freeze_identity"]==b["research_freeze_identity"]
 assert a["candidate_universe_hash"]==b["candidate_universe_hash"] and len(a["models"])==36
 changed=list(entries);changed[0]=replace(changed[0],secondary_traits=("ema",)); assert build_freeze_manifest(changed,CURRENT_PROTOCOL_SCOPE,LOCK,"abc")["research_freeze_identity"]!=a["research_freeze_identity"]
 changed=list(entries);changed[0]=replace(changed[0],parameter_grid_hash="x"*64); assert build_freeze_manifest(changed,CURRENT_PROTOCOL_SCOPE,LOCK,"abc")["research_freeze_identity"]!=a["research_freeze_identity"]
 changed=list(entries);changed[0]=replace(changed[0],implementation_module_hash="y"*64); assert build_freeze_manifest(changed,CURRENT_PROTOCOL_SCOPE,LOCK,"abc")["research_freeze_identity"]!=a["research_freeze_identity"]
 for field,value in (("symbols",("X",)),("timeframe","4h"),("engine_identity","other"),("cost_model_identity","other"),("causal_execution_policy","other")):
  assert build_freeze_manifest(entries,replace(CURRENT_PROTOCOL_SCOPE,**{field:value}),LOCK,"abc")["research_freeze_identity"]!=a["research_freeze_identity"]
 lock=dict(LOCK);lock["actual_end"]="changed"; assert build_freeze_manifest(entries,CURRENT_PROTOCOL_SCOPE,lock,"abc")["research_freeze_identity"]!=a["research_freeze_identity"]
 source=(ROOT / "quantbot/research/freeze_manifest.py").read_text(encoding="utf-8"); assert "d2_oos" not in source and "d3_oos" not in source
 print("FREEZE_MANIFEST_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
