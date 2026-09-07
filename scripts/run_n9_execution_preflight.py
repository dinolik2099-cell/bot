"""Metadata-only N9 manifest/preflight wiring; never reads market data."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest
def main():
 lock=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());n7=load_n7_context(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json',ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json',lock);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json');m=build_manifest(n7,n8,source_git_commit='143ebbab0b657646a8c59d55aad7099b9ea0eaf1',worker_config={'workers':1},output_destination='data/reports/N9_FORMAL_RESULT.json',created_at='runtime')
 print('N9_PREFLIGHT_OK');print(f"manifest_identity={m['manifest_identity']}");print(f"market_data_reads=0");print(f"oos_status={m['oos_status']}");print(f"oos_authorization={m['oos_authorization']}")
if __name__=='__main__':main()
