"""Read-only N7 chain preflight; it does not create a data loader or run research."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
def main():
 ap=argparse.ArgumentParser(description='Validate N7 formal-run prerequisites without market-data access.')
 ap.add_argument('--plan',default=str(ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json'))
 ap.add_argument('--freeze',default=str(ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'))
 ap.add_argument('--boundary-lock',default=str(ROOT/'data/reports/research_boundary_lock.json'))
 args=ap.parse_args();context=load_n7_context(args.plan,args.freeze,json.loads(Path(args.boundary_lock).read_text(encoding='utf-8')));plan=context.plan
 print('N7_PREFLIGHT_OK')
 for key,value in sorted({'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'models':len(plan['models']),'symbols':len(plan['symbols']),'tasks':len(plan['tasks']),'expected_train_evaluations':plan['counts']['train_evaluations'],'maximum_validation_evaluations':plan['counts']['validation_evaluations_max'],'engine_identity':context.freeze['protocol_scope']['engine_identity'],'cost_model_identity':context.freeze['protocol_scope']['cost_model_identity'],'oos_status':plan['oos_status'],'oos_authorization':plan['oos_authorization']}.items()):print(f'{key}={value}')
if __name__=='__main__':main()
