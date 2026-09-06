from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE,build_candidate_universe
from quantbot.research.research_plan import build_plan
from quantbot.research.model_registry import register_existing_models
from quantbot.strategies.model_pool import register_model_pool
def main():
 out=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json'
 if out.exists():raise FileExistsError(out)
 freeze=json.loads((ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json').read_text())
 lock=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text())
 register_existing_models();register_model_pool()
 p=build_plan(build_candidate_universe(),CURRENT_PROTOCOL_SCOPE,lock,freeze['research_freeze_identity'])
 out.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n');print('RESEARCH_PLAN_ARTIFACT_OK',p['research_plan_identity'])
if __name__=='__main__':main()
